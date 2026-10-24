import logging
import re
import smtplib
import threading
from dataclasses import dataclass, replace
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from html import unescape
from typing import TYPE_CHECKING

from app.config import settings
from app.utils.money import utcnow

if TYPE_CHECKING:
    from fastapi import BackgroundTasks
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def dispatch_email_task(background_tasks: "BackgroundTasks | None", db: "Session", target, *args, **kwargs) -> None:
    """Schedule `target(db, *args, **kwargs)` so the caller (a booking/
    payment request) never blocks on SMTP.

    - When `background_tasks` (FastAPI's BackgroundTasks) is available, the
      task runs after the response is sent, still safely reusing the
      request's `db` session - FastAPI defers closing yield-based
      dependencies (like the request's DB session) until after background
      tasks finish, precisely so this is safe.
    - When no BackgroundTasks is available (e.g. this helper end up being
      called from a background sweep rather than an HTTP request, or from a
      service layer that hasn't threaded one through), falls back to a
      daemon thread. That thread opens its OWN DB session rather than
      reusing `db`, since the caller's session may already be closed, or
      concurrently in use on another thread, by the time the thread runs.
    Either way, a failed/slow send is caught and logged as a warning - it
    must never surface to, or block, the original caller.
    """
    if background_tasks is not None:
        background_tasks.add_task(_run_email_task, db, target, args, kwargs)
        return

    def _run_in_thread() -> None:
        from app.database import SessionLocal

        thread_db = SessionLocal()
        try:
            _run_email_task(thread_db, target, args, kwargs)
        finally:
            thread_db.close()

    threading.Thread(target=_run_in_thread, daemon=True).start()


def _run_email_task(db: "Session", target, args: tuple, kwargs: dict) -> None:
    try:
        target(db, *args, **kwargs)
    except Exception:
        logger.warning("Background email task %s failed", getattr(target, "__name__", target), exc_info=True)


@dataclass(frozen=True)
class EmailSendResult:
    ok: bool
    status: str
    message_id: str
    error: str = ""


@dataclass(frozen=True)
class _SmtpConfig:
    host: str | None
    port: int
    username: str | None
    password: str | None
    from_name: str
    from_email: str | None
    reply_to: str | None
    use_ssl: bool
    use_starttls: bool
    timeout_seconds: int


def _normalise_smtp_transport(config: _SmtpConfig) -> _SmtpConfig:
    """Keep implicit TLS and STARTTLS mutually exclusive.

    SMTP over implicit TLS (the normal port-465 setup) is already encrypted
    when the connection opens. Retaining a STARTTLS setting alongside it is
    misleading and could become a delivery failure if this transport changes.
    Prefer SSL because it is the configured port-465 mode.
    """
    if config.use_ssl and config.use_starttls:
        logger.warning("SMTP has both SSL and STARTTLS enabled; using SSL only")
        return replace(config, use_starttls=False)
    return config


def _env_smtp_config() -> _SmtpConfig:
    return _normalise_smtp_transport(_SmtpConfig(
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME or settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        from_name=settings.SMTP_FROM_NAME,
        from_email=settings.SMTP_FROM_EMAIL,
        reply_to=settings.SMTP_REPLY_TO,
        use_ssl=settings.SMTP_USE_SSL,
        use_starttls=settings.SMTP_STARTTLS,
        timeout_seconds=settings.SMTP_TIMEOUT_SECONDS,
    ))


def _effective_smtp_config() -> _SmtpConfig:
    """DB-backed SMTP settings (Settings > Email/SMTP) take effect when
    explicitly enabled; otherwise fall back to the env-var config exactly as
    before. Any failure reading the DB (table not migrated yet, connection
    issue) silently falls back to env vars rather than breaking outbound
    email -- same "degrade gracefully" approach used for approval_history."""
    try:
        from app.database import SessionLocal
        from app.models.settings import SmtpSetting
        from app.utils.crypto import decrypt_secret

        db = SessionLocal()
        try:
            row = db.query(SmtpSetting).first()
            if row and row.is_enabled and row.host:
                return _normalise_smtp_transport(_SmtpConfig(
                    host=row.host,
                    port=row.port,
                    username=row.username or None,
                    password=decrypt_secret(row.password or "") or None,
                    from_name=row.from_name,
                    from_email=row.from_email or None,
                    reply_to=row.reply_to or None,
                    use_ssl=row.use_ssl,
                    use_starttls=row.use_starttls,
                    timeout_seconds=row.timeout_seconds,
                ))
            if row and not (row.is_enabled and row.host):
                # A row exists (someone opened Settings > Email/SMTP and saved
                # something) but it's disabled or missing a host, so we're
                # about to fall back to env vars - without this line that
                # fallback is invisible, and env vars are frequently unset in
                # production, producing the exact "no error, email just never
                # arrives" symptom this is meant to catch.
                logger.warning("DB SMTP settings row exists but is_enabled=%s host=%r - falling back to env config", row.is_enabled, row.host)
        finally:
            db.close()
    except Exception as error:
        # This used to log at debug level, which production log levels
        # (typically INFO/WARNING) filter out entirely - a DB lookup failure
        # here silently falls back to (often unset) env vars, which is
        # exactly the kind of "email just doesn't send" symptom with no
        # visible cause that this flow has been hit by.
        logger.warning("Could not load DB SMTP settings, using env config: %s", error)

    return _env_smtp_config()


def _domain_from_email(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if "@" in email else "tourvaa.com"


def _plain_text_from_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip() or "Please view this email in an HTML email client."


def _single_line_header(value: str, field_name: str) -> str:
    """Reject header injection and keep SMTP headers standards compliant."""
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    if "\r" in cleaned or "\n" in cleaned:
        raise ValueError(f"{field_name} must be a single line")
    return cleaned


def _mailbox(value: str, field_name: str) -> str:
    cleaned = _single_line_header(value, field_name)
    display_name, address = parseaddr(cleaned)
    if display_name or address != cleaned or "@" not in address:
        raise ValueError(f"{field_name} must contain one email address")
    local, domain = address.rsplit("@", 1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError(f"{field_name} must contain a valid email address")
    return address


def _create_email_log(
    to_email: str,
    subject: str,
    status: str,
    error_message: str = "",
    template_key: str = "smtp",
    entity_type: str = "email",
    entity_id: int | None = None,
) -> int | None:
    try:
        from app.database import SessionLocal
        from app.models.bookings import EmailLog

        db = SessionLocal()
        try:
            row = EmailLog(
                recipient_email=to_email,
                subject=subject,
                template_key=template_key or "smtp",
                entity_type=entity_type,
                entity_id=entity_id,
                status=status,
                error_message=error_message or None,
                sent_at=utcnow() if status == "sent" else None,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id
        finally:
            db.close()
    except Exception as error:
        logger.debug("Could not create email log: %s", error)
        return None


def _update_email_log(log_id: int | None, status: str, error_message: str = "") -> None:
    if not log_id:
        return
    try:
        from app.database import SessionLocal
        from app.models.bookings import EmailLog

        db = SessionLocal()
        try:
            row = db.query(EmailLog).filter(EmailLog.id == log_id).first()
            if row:
                row.status = status
                row.error_message = error_message or None
                row.sent_at = utcnow() if status == "sent" else row.sent_at
                db.commit()
        finally:
            db.close()
    except Exception as error:
        logger.debug("Could not update email log %s: %s", log_id, error)


def _build_message(config: _SmtpConfig, to_email: str, subject: str, html: str, attachments: list[tuple[str, bytes, str]] | None = None) -> tuple[EmailMessage, str]:
    smtp_user = config.username
    from_email = config.from_email or smtp_user

    missing = [
        name for name, value in (
            ("host", config.host),
            ("username", smtp_user),
            ("password", config.password),
            ("from_email", from_email),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"SMTP configuration is incomplete - missing: {', '.join(missing)}")

    from_email = _mailbox(from_email, "from_email")
    to_email = _mailbox(to_email, "to_email")
    subject = _single_line_header(subject, "subject")
    from_name = _single_line_header(config.from_name or "Tourvaa", "from_name")
    reply_to = _mailbox(config.reply_to or from_email, "reply_to")

    message_id = make_msgid(domain=_domain_from_email(from_email))
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((from_name, from_email))
    message["To"] = to_email
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = message_id
    message["X-Auto-Response-Suppress"] = "All"
    message["Auto-Submitted"] = "auto-generated"
    message["Reply-To"] = reply_to

    message.set_content(_plain_text_from_html(html))
    message.add_alternative(html, subtype="html")

    for filename, data, subtype in attachments or []:
        maintype = "application"
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    return message, message_id


def send_email(
    to_email: str,
    subject: str,
    html: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
    template_key: str = "smtp",
    entity_type: str = "email",
    entity_id: int | None = None,
) -> EmailSendResult:
    log_id = _create_email_log(
        to_email,
        subject,
        "sending",
        template_key=template_key,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    message_id = ""

    try:
        config = _effective_smtp_config()
        message, message_id = _build_message(config, to_email, subject, html, attachments)
        smtp_user = config.username or ""

        if config.use_ssl:
            with smtplib.SMTP_SSL(
                config.host,
                config.port,
                timeout=config.timeout_seconds,
            ) as smtp:
                smtp.login(smtp_user, config.password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(
                config.host,
                config.port,
                timeout=config.timeout_seconds,
            ) as smtp:
                smtp.ehlo()
                if config.use_starttls:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(smtp_user, config.password)
                smtp.send_message(message)

        _update_email_log(log_id, "sent")
        logger.info("Email sent to %s subject=%r message_id=%s", to_email, subject, message_id)
        return EmailSendResult(ok=True, status="sent", message_id=message_id)
    except Exception as error:
        error_message = str(error)
        _update_email_log(log_id, "failed", error_message)
        logger.warning("Could not send email to %s: %s", to_email, error_message)
        raise


def try_send_email(
    to_email: str,
    subject: str,
    html: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
    template_key: str = "smtp",
    entity_type: str = "email",
    entity_id: int | None = None,
) -> bool:
    try:
        send_email(
            to_email,
            subject,
            html,
            attachments,
            template_key=template_key,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        return True
    except Exception:
        return False
