"""Print the saved SMTP configuration without revealing its password."""

from app.database import SessionLocal
from app.models.settings import SmtpSetting


if __name__ == "__main__":
    db = SessionLocal()
    try:
        for setting in db.query(SmtpSetting).order_by(SmtpSetting.id).all():
            print({
                "id": setting.id,
                "is_enabled": setting.is_enabled,
                "host": setting.host,
                "port": setting.port,
                "username": setting.username,
                "from_name": setting.from_name,
                "from_email": setting.from_email,
                "reply_to": setting.reply_to,
                "use_ssl": setting.use_ssl,
                "use_starttls": setting.use_starttls,
                "timeout_seconds": setting.timeout_seconds,
            })
    finally:
        db.close()
