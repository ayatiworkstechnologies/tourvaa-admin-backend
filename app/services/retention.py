"""Retention cleanup for fast-growing, non-financial/non-audit log tables.

Deliberately out of scope (legal/financial retention requirements - never
touched here): audit_logs, payments, payment_transactions, payment_holds,
invoices, invoice_items, bookings and all booking_* tables, supplier_ledger,
agent_ledger, and anything else recording money movement or an audit trail.

Chat bot data (chat_sessions/chat_messages/chat_feedback) already has its own
90-day retention sweep - see purge_old_chat_data() in app/services/chatbot.py,
wired up via app.main._chat_retention_loop(). Not duplicated here.

Each table's cleanup is independent and defensive: one table failing (locked
row, unexpected schema drift, etc.) must not stop the others from running.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.notifications import Notification
from app.models.sessions import LoginHistory, UserSession
from app.models.bookings import EmailLog

logger = logging.getLogger(__name__)

# Named constants so thresholds are easy to tune later without hunting
# through the cleanup logic itself.
LOGIN_HISTORY_RETENTION_DAYS = 180
EMAIL_LOG_RETENTION_DAYS = 270
NOTIFICATION_RETENTION_DAYS = 90
SESSION_RETENTION_DAYS = 90

# Statuses that mean a session is no longer live (see app/services/sessions.py)
_INACTIVE_SESSION_STATUSES = ("revoked", "expired")


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _cleanup_login_history(db: Session) -> int:
    cutoff = _cutoff(LOGIN_HISTORY_RETENTION_DAYS)
    count = (
        db.query(LoginHistory)
        .filter(LoginHistory.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return count


def _cleanup_email_logs(db: Session) -> int:
    cutoff = _cutoff(EMAIL_LOG_RETENTION_DAYS)
    count = (
        db.query(EmailLog)
        .filter(EmailLog.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return count


def _cleanup_notifications(db: Session) -> int:
    # Only ever remove notifications the user has already read/dismissed -
    # unread notifications are left alone regardless of age.
    cutoff = _cutoff(NOTIFICATION_RETENTION_DAYS)
    count = (
        db.query(Notification)
        .filter(Notification.created_at < cutoff, Notification.is_read == 1)
        .delete(synchronize_session=False)
    )
    db.commit()
    return count


def _cleanup_sessions(db: Session) -> int:
    # Only revoked/expired sessions - an active session is never deleted
    # here regardless of age.
    cutoff = _cutoff(SESSION_RETENTION_DAYS)
    count = (
        db.query(UserSession)
        .filter(
            UserSession.status.in_(_INACTIVE_SESSION_STATUSES),
            UserSession.created_at < cutoff,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return count


def run_retention_cleanup(db: Session) -> dict[str, int]:
    """Run all retention cleanups. Each table is wrapped in its own
    try/except so one failure (e.g. a lock timeout) doesn't stop the rest -
    consistent with how the other background sweeps in this codebase
    (app/main.py) isolate failures per-job."""
    results: dict[str, int] = {}

    jobs = (
        ("login_history", _cleanup_login_history),
        ("email_logs", _cleanup_email_logs),
        ("notifications", _cleanup_notifications),
        ("user_sessions", _cleanup_sessions),
    )

    for name, job in jobs:
        try:
            deleted = job(db)
            results[name] = deleted
            if deleted:
                logger.info("Retention cleanup: removed %d row(s) from %s", deleted, name)
        except Exception:
            db.rollback()
            logger.warning("Retention cleanup failed for %s", name, exc_info=True)

    return results
