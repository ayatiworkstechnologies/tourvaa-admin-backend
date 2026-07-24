from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.agents import Agent
from app.models.customers import Customer
from app.models.suppliers import Supplier
from app.services import auth
from app.utils import notification_triggers


@pytest.mark.parametrize(
    ("user_type", "profile_model"),
    [
        ("CUSTOMER", Customer),
        ("AGENT", Agent),
        ("SUPPLIER", Supplier),
    ],
)
def test_password_creation_activates_every_registration_type(monkeypatch, user_type, profile_model):
    user = SimpleNamespace(
        id=42,
        user_type=user_type,
        account_status="PENDING_PASSWORD_CREATION",
        is_active=False,
        approval_status="pending",
        password=None,
        password_created_at=None,
        email_verified=False,
        email_verified_at=None,
        email_verification_token="hashed-token",
        email_verification_expires_at=object(),
    )
    customer = SimpleNamespace(email_verified=False, status="inactive")
    agent = SimpleNamespace(
        status="inactive",
        approval_status="email_verification_pending",
        approved_at=None,
        rejection_reason="",
    )
    supplier = SimpleNamespace(
        id=99,
        supplier_name="Test Supplier",
        status="inactive",
        approval_status="email_verification_pending",
        approved_at=None,
        rejection_reason="",
    )
    profiles = {
        Customer: customer if profile_model is Customer else None,
        Agent: agent if profile_model is Agent else None,
        Supplier: supplier if profile_model is Supplier else None,
    }
    db = MagicMock()

    def query(model):
        result = MagicMock()
        result.filter.return_value.first.return_value = profiles[model]
        return result

    db.query.side_effect = query
    monkeypatch.setattr(auth, "_registration_token_user", lambda _db, _token: user)
    monkeypatch.setattr(auth, "hash_password", lambda _password: "hashed-password")
    monkeypatch.setattr(auth, "UserStatusHistory", lambda **values: SimpleNamespace(**values))
    monkeypatch.setattr(notification_triggers, "notify_supplier_approval_pending", lambda *_args, **_values: None)

    result = auth.complete_registration(db, "raw-token", "StrongPass1!")

    assert result is user
    assert user.password == "hashed-password"
    assert user.email_verified is True
    assert user.account_status == "ACTIVE"
    assert user.is_active is True
    expected_approval = "PENDING" if user_type == "SUPPLIER" else "NOT_REQUIRED"
    assert user.approval_status == expected_approval
    selected_profile = profiles[profile_model]
    assert selected_profile.status == "active"
    if profile_model is Customer:
        assert selected_profile.email_verified is True
    elif profile_model is Agent:
        assert selected_profile.approval_status == "NOT_REQUIRED"
    else:
        assert selected_profile.approval_status == "PENDING"
    history = next(
        call.args[0]
        for call in db.add.call_args_list
        if hasattr(call.args[0], "from_status")
    )
    assert history.from_status == "PENDING_PASSWORD_CREATION"
    assert history.to_status == "ACTIVE"
    assert "activated" in history.reason
    db.commit.assert_called_once()
