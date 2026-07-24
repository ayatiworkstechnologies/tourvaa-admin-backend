import logging
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import unescape

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailSendResult:
    ok: bool
    status: str
    message_id: str
    error: str = ""


def _smtp_user() -> str | None:
    return settings.SMTP_USERNAME or settings.SMTP_USER


def _from_email() -> str | None:
    return settings.SMTP_FROM_EMAIL or _smtp_user()


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


def _create_email_log(to_email: str, subject: str, status: str, error_message: str = "") -> int | None:
    try:
        from app.database import SessionLocal
        from app.models.bookings import EmailLog

        db = SessionLocal()
        try:
            row = EmailLog(
                recipient_email=to_email,
                subject=subject,
                template_key="smtp",
                entity_type="email",
                status=status,
                error_message=error_message or None,
                sent_at=datetime.utcnow() if status == "sent" else None,
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
                row.sent_at = datetime.utcnow() if status == "sent" else row.sent_at
                db.commit()
        finally:
            db.close()
    except Exception as error:
        logger.debug("Could not update email log %s: %s", log_id, error)


def _build_message(to_email: str, subject: str, html: str) -> tuple[EmailMessage, str]:
    smtp_user = _smtp_user()
    from_email = _from_email()

    if not settings.SMTP_HOST or not smtp_user or not settings.SMTP_PASSWORD or not from_email:
        raise RuntimeError("SMTP configuration is incomplete")

    message_id = make_msgid(domain=_domain_from_email(from_email))
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.SMTP_FROM_NAME, from_email))
    message["To"] = to_email
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = message_id
    message["X-Mailer"] = "Tourvaa SMTP"
    message["X-Auto-Response-Suppress"] = "All"

    reply_to = settings.SMTP_REPLY_TO or from_email
    if reply_to:
        message["Reply-To"] = reply_to

    message.set_content(_plain_text_from_html(html))
    message.add_alternative(html, subtype="html")
    return message, message_id


def send_email(to_email: str, subject: str, html: str) -> EmailSendResult:
    log_id = _create_email_log(to_email, subject, "sending")
    message_id = ""

    try:
        message, message_id = _build_message(to_email, subject, html)
        smtp_user = _smtp_user() or ""

        if settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
            ) as smtp:
                smtp.login(smtp_user, settings.SMTP_PASSWORD)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
            ) as smtp:
                smtp.ehlo()
                if settings.SMTP_STARTTLS:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(smtp_user, settings.SMTP_PASSWORD)
                smtp.send_message(message)

        _update_email_log(log_id, "sent")
        logger.info("Email sent to %s subject=%r message_id=%s", to_email, subject, message_id)
        return EmailSendResult(ok=True, status="sent", message_id=message_id)
    except Exception as error:
        error_message = str(error)
        _update_email_log(log_id, "failed", error_message)
        logger.warning("Could not send email to %s: %s", to_email, error_message)
        raise


def try_send_email(to_email: str, subject: str, html: str) -> bool:
    try:
        send_email(to_email, subject, html)
        return True
    except Exception:
        return False
