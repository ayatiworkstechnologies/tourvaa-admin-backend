from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

# Importing the application registers every SQLAlchemy relationship target.
from app.main import app as _app  # noqa: F401
from app.models.agents import Agent
from app.models.customers import Customer
from app.models.roles import Role
from app.models.suppliers import Supplier
from app.models.users import User
from app.middleware.error_handlers import register_error_handlers
from app.schemas.auth import UnifiedRegisterSchema
from app.services import auth


def registration_data(account_type: str, **overrides):
    values = {
        "account_type": account_type,
        "first_name": "Tourvaa User",
        "email": f"{account_type.lower()}@example.com",
        "country_code": "+91",
        "mobile_number": "9876543210",
        "accepted_terms": True,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("account_type", ["CUSTOMER", "AGENT", "SUPPLIER"])
def test_all_public_roles_use_the_same_passwordless_schema(account_type):
    parsed = UnifiedRegisterSchema(**registration_data(account_type))
    assert parsed.account_type == account_type
    assert "password" not in parsed.model_dump()


def test_role_policy_validation_returns_serializable_422():
    test_app = FastAPI()
    register_error_handlers(test_app)

    @test_app.post("/register")
    def register(data: UnifiedRegisterSchema):
        return data

    response = TestClient(test_app).post(
        "/register",
        json=registration_data("CUSTOMER", accepted_terms=False),
    )

    assert response.status_code == 422
    assert response.json()["status"] == "error"
    assert "accept the Terms" in response.json()["message"]


@pytest.mark.parametrize(
    ("account_type", "role_slug", "profile_model", "approval_status"),
    [
        ("CUSTOMER", "customer", Customer, "NOT_REQUIRED"),
        ("AGENT", "agent-reseller", Agent, "NOT_REQUIRED"),
        ("SUPPLIER", "supplier", Supplier, "PENDING"),
    ],
)
def test_every_role_starts_email_verification(monkeypatch, account_type, role_slug, profile_model, approval_status):
    data = UnifiedRegisterSchema(**registration_data(account_type))
    role = SimpleNamespace(id=7, slug=role_slug, is_active=True)
    db = MagicMock()

    def query(model):
        result = MagicMock()
        result.filter.return_value.first.return_value = role if model is Role else None
        return result

    db.query.side_effect = query
    monkeypatch.setattr(auth, "create_password_reset_token", lambda: ("raw-token", "hashed-token"))
    send_verification = MagicMock()
    monkeypatch.setattr(auth, "send_email_verification", send_verification)

    user = auth.register_unified_user(db, data)

    assert user.account_status == "PENDING_EMAIL_VERIFICATION"
    assert user.is_active is False
    assert user.password is None
    assert user.approval_status == approval_status
    assert user.email_verification_token == "hashed-token"
    added = [call.args[0] for call in db.add.call_args_list]
    profile = next(item for item in added if isinstance(item, profile_model))
    assert profile.status == "inactive"
    if isinstance(profile, Agent):
        assert profile.approval_status == "NOT_REQUIRED"
    if isinstance(profile, Supplier):
        assert profile.approval_status == "PENDING"
    send_verification.assert_called_once_with(db, user, "raw-token", None)
