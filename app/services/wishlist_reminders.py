"""Weekly wishlist reminder emails (client feedback, page 15: "If a User
adds the Tour to a wishlist, we need to able to reminder emails in
intervals of time i.e. every week"). One email per user, batching every
tour they've wishlisted that's due for its weekly reminder, following the
dedup pattern in app.services.invoices.check_balance_due_reminders.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.cms import Tour
from app.models.customers import CustomerWishlistItem
from app.models.users import User

logger = logging.getLogger(__name__)

_REMINDER_INTERVAL = timedelta(days=7)


def check_wishlist_reminders(db: Session) -> None:
    from app.schemas.cms import slugify
    from app.utils.mailer import try_send_email

    now = datetime.now(timezone.utc)
    cutoff = now - _REMINDER_INTERVAL

    due_items = (
        db.query(CustomerWishlistItem)
        .filter(
            (CustomerWishlistItem.last_reminder_sent_at.is_(None)) | (CustomerWishlistItem.last_reminder_sent_at <= cutoff)
        )
        .all()
    )
    if not due_items:
        return

    by_user: dict[int, list[CustomerWishlistItem]] = {}
    for item in due_items:
        by_user.setdefault(item.user_id, []).append(item)

    for user_id, items in by_user.items():
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.email:
                continue

            rows = []
            for item in items:
                tour = db.query(Tour).filter(Tour.id == item.tour_id, Tour.status == "published").first()
                if not tour:
                    continue
                country_slug = slugify(tour.country.country_name if tour.country else "worldwide")
                url = f"{settings.FRONTEND_URL}/tours/{country_slug}/{tour.slug}"
                rows.append(f"<li><a href=\"{url}\">{tour.title}</a></li>")

            if not rows:
                for item in items:
                    item.last_reminder_sent_at = now
                db.commit()
                continue

            subject = "Your Tourvaa wishlist is waiting"
            body = (
                f"<p>Hi {user.name or 'there'},</p>"
                f"<p>Here's a reminder of the tours on your Tourvaa wishlist:</p>"
                f"<ul>{''.join(rows)}</ul>"
                f"<p>Book now before seats fill up.</p>"
            )
            try_send_email(user.email, subject, body, template_key="wishlist_reminder")

            for item in items:
                item.last_reminder_sent_at = now
            db.commit()
        except Exception:
            logger.exception("Failed to send wishlist reminder for user_id=%s", user_id)
            db.rollback()
