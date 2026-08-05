import logging
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import unescape

from app.config import settings
from app.utils.money import utcnow

logger = logging.getLogger(__name__)


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


def _env_smtp_config() -> _SmtpConfig:
    return _SmtpConfig(
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
    )


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
                return _SmtpConfig(
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
                )
        finally:
            db.close()
    except Exception as error:
        logger.debug("Could not load DB SMTP settings, using env config: %s", error)

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


def _create_email_log(to_email: str, subject: str, status: str, error_message: str = "", template_key: str = "smtp") -> int | None:
    try:
        from app.database import SessionLocal
        from app.models.bookings import EmailLog

        db = SessionLocal()
        try:
            row = EmailLog(
                recipient_email=to_email,
                subject=subject,
                template_key=template_key or "smtp",
                entity_type="email",
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

    if not config.host or not smtp_user or not config.password or not from_email:
        raise RuntimeError("SMTP configuration is incomplete")

    message_id = make_msgid(domain=_domain_from_email(from_email))
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((config.from_name, from_email))
    message["To"] = to_email
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = message_id
    message["X-Mailer"] = "Tourvaa SMTP"
    message["X-Auto-Response-Suppress"] = "All"

    reply_to = config.reply_to or from_email
    if reply_to:
        message["Reply-To"] = reply_to

    message.set_content(_plain_text_from_html(html))
    message.add_alternative(html, subtype="html")

    for filename, data, subtype in attachments or []:
        maintype = "application"
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    return message, message_id


def send_email(to_email: str, subject: str, html: str, attachments: list[tuple[str, bytes, str]] | None = None, template_key: str = "smtp") -> EmailSendResult:
    log_id = _create_email_log(to_email, subject, "sending", template_key=template_key)
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


def try_send_email(to_email: str, subject: str, html: str, attachments: list[tuple[str, bytes, str]] | None = None, template_key: str = "smtp") -> bool:
    try:
        send_email(to_email, subject, html, attachments, template_key=template_key)
        return True
    except Exception:
        return False
