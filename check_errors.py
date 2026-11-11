"""Print recent SMTP authentication and recipient failures without DB secrets."""

from app.database import SessionLocal
from app.models.bookings import EmailLog


def report(error_code: str, label: str) -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(EmailLog)
            .filter(EmailLog.error_message.like(f"%{error_code}%"))
            .order_by(EmailLog.id.desc())
            .limit(10)
            .all()
        )
        print(f"=== {label} (latest {len(rows)}) ===")
        for row in rows:
            print(f"ID: {row.id} | To: {row.recipient_email} | Error: {(row.error_message or '')[:120]} | At: {row.sent_at}")
        print()
    finally:
        db.close()


if __name__ == "__main__":
    report("535", "535 Authentication Errors")
    report("550", "550 Recipient/Delivery Errors")
