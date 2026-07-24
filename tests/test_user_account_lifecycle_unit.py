from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services import users as user_service


def inactive_supplier(**overrides):
    values = {
        "id": 22,
        "name": "Supplier",
        "email": "supplier@example.com",
        "user_type": "SUPPLIER",
        "account_status": "INACTIVE",
        "is_active": False,
        "password_created_at": datetime.utcnow(),
        "email_verified": True,
        "email_verified_at": datetime.utcnow(),
        "admin_verified": True,
        "admin_verified_at": datetime.utcnow(),
        "admin_verified_by": 1,
        "deactivated_at": datetime.utcnow(),
        "deactivated_by": 1,
        "deactivation_reason": "Paused",
        "token_version": 3,
        "role": SimpleNamespace(slug="supplier"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_reactivate_supplier_restores_login_without_approving_operations(monkeypatch):
    user = inactive_supplier()
    supplier = SimpleNamespace(status="inactive", approval_status="PENDING")
    actor = SimpleNamespace(id=1)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = supplier

    monkeypatch.setattr(user_service, "get_user_by_id", lambda *_: user)
    monkeypatch.setattr(
        user_service,
        "serialize_user",
        lambda value: {
            "id": value.id,
            "account_status": value.account_status,
            "is_active": value.is_active,
        },
    )
    monkeypatch.setattr(user_service, "log_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        user_service,
        "UserStatusHistory",
        lambda **values: SimpleNamespace(**values),
    )
    monkeypatch.setattr(
        user_service,
        "render_database_email",
        lambda *args, **kwargs: ("Account active", "<p>Active</p>"),
    )
    monkeypatch.setattr(user_service, "try_send_email", lambda *args, **kwargs: None)

    result = user_service.reactivate_user(db, user.id, actor=actor)

    assert result["account_status"] == "ACTIVE"
    assert result["is_active"] is True
    assert user.deactivated_at is None
    assert user.deactivation_reason is None
    assert user.token_version == 4
    assert supplier.status == "active"
    assert supplier.approval_status == "PENDING"
    history = db.add.call_args.args[0]
    assert history.from_status == "INACTIVE"
    assert history.to_status == "ACTIVE"
    db.commit.assert_called_once()


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"password_created_at": None}, "Password creation"),
        ({"email_verified": False}, "Email verification"),
        ({"email_verified_at": None}, "Email verification"),
    ],
)
def test_reactivate_public_account_requires_completed_registration(monkeypatch, changes, expected):
    user = inactive_supplier(**changes)
    monkeypatch.setattr(user_service, "get_user_by_id", lambda *_: user)

    with pytest.raises(HTTPException) as raised:
        user_service.reactivate_user(MagicMock(), user.id)

    assert raised.value.status_code == 400
    assert expected in raised.value.detail


def test_users_router_exposes_separate_reactivation_endpoint():
    from app.main import app

    assert "post" in app.openapi()["paths"]["/api/users/{user_id}/reactivate"]
