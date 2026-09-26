from unittest.mock import Mock

from app.services import retention


def test_retention_cleanup_runs_every_job_and_reports_counts(monkeypatch):
    db = Mock()
    expected = {
        "login_history": 2,
        "email_logs": 3,
        "notifications": 5,
        "user_sessions": 7,
    }

    monkeypatch.setattr(retention, "_cleanup_login_history", lambda session: expected["login_history"])
    monkeypatch.setattr(retention, "_cleanup_email_logs", lambda session: expected["email_logs"])
    monkeypatch.setattr(retention, "_cleanup_notifications", lambda session: expected["notifications"])
    monkeypatch.setattr(retention, "_cleanup_sessions", lambda session: expected["user_sessions"])

    assert retention.run_retention_cleanup(db) == expected
    db.rollback.assert_not_called()


def test_retention_cleanup_isolates_a_failed_table(monkeypatch):
    db = Mock()

    def fail(_db):
        raise RuntimeError("locked table")

    monkeypatch.setattr(retention, "_cleanup_login_history", lambda session: 1)
    monkeypatch.setattr(retention, "_cleanup_email_logs", fail)
    monkeypatch.setattr(retention, "_cleanup_notifications", lambda session: 3)
    monkeypatch.setattr(retention, "_cleanup_sessions", lambda session: 4)

    assert retention.run_retention_cleanup(db) == {
        "login_history": 1,
        "notifications": 3,
        "user_sessions": 4,
    }
    db.rollback.assert_called_once_with()
