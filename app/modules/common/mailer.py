import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings


def send_email(to_email: str, subject: str, html: str):
    smtp_user = settings.SMTP_USERNAME or settings.SMTP_USER

    if not settings.SMTP_HOST or not smtp_user or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP configuration is incomplete")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.SMTP_FROM_NAME, smtp_user))
    message["To"] = to_email
    message.set_content("Please view this email in an HTML email client.")
    message.add_alternative(html, subtype="html")

    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
        smtp.login(smtp_user, settings.SMTP_PASSWORD)
        smtp.send_message(message)
