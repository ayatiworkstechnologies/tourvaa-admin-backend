import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterSchema, ResetPasswordSchema
from app.schemas.users import UserCreate
from app.services.auth import verify_email
from app.auth.security import hash_reset_token


VALID_USER = {
    "name": "QA User",
    "email": "qa-strong@example.com",
    "phone": "+919876543210",
    "password": "Strong@123",
}


@pytest.mark.parametrize("schema", [RegisterSchema, UserCreate])
def test_registration_schemas_require_strong_password(schema):
    with pytest.raises(ValidationError):
        schema(**{**VALID_USER, "password": "password"})

    parsed = schema(**VALID_USER)
    assert parsed.password == "Strong@123"


def test_reset_password_schema_requires_strong_password():
    with pytest.raises(ValidationError):
        ResetPasswordSchema(token="token", password="password")

    parsed = ResetPasswordSchema(token="token", password="Strong@123")
    assert parsed.password == "Strong@123"


def test_backend_private_key_files_are_not_tracked():
    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "ls-files", "*.pem", "vapid_private.pem"],
        cwd=backend_dir,
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        pytest.skip("backend directory is not a git checkout")

    assert result.stdout.strip() == ""


def test_payments_are_internal_ledger_not_gateway_webhooks():
    backend_dir = Path(__file__).resolve().parents[1]
    payment_router = (backend_dir / "app" / "routers" / "payments.py").read_text(encoding="utf-8")
    payment_service = (backend_dir / "app" / "services" / "payments.py").read_text(encoding="utf-8")

    assert "/webhook" not in payment_router.lower()
    assert "stripe." not in payment_service.lower()
    assert "paypal" not in payment_service.lower()


class _FakeUserQuery:
    def __init__(self, user):
        self.user = user

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.user


class _FakeDb:
    def __init__(self, user):
        self.user = user
        self.committed = False

    def query(self, _model):
        return _FakeUserQuery(self.user)

    def commit(self):
        self.committed = True


def test_verify_email_consumes_valid_registration_token():
    token = "registration-token"
    user = SimpleNamespace(
        email_verification_token=hash_reset_token(token),
        email_verification_expires_at=datetime.utcnow() + timedelta(minutes=5),
        email_verified_at=None,
    )
    db = _FakeDb(user)

    assert verify_email(db, token) is True
    assert db.committed is True
    assert user.email_verified_at is not None
    assert user.email_verification_token is None
    assert user.email_verification_expires_at is None


def test_verify_email_rejects_expired_registration_token():
    token = "expired-token"
    user = SimpleNamespace(
        email_verification_token=hash_reset_token(token),
        email_verification_expires_at=datetime.utcnow() - timedelta(minutes=5),
        email_verified_at=None,
    )
    db = _FakeDb(user)

    with pytest.raises(Exception):
        verify_email(db, token)
    assert db.committed is False


def test_auth_router_exposes_spec_registration_routes():
    backend_dir = Path(__file__).resolve().parents[1]
    auth_router = (backend_dir / "app" / "routers" / "auth.py").read_text(encoding="utf-8")

    assert '@router.post("/register/customer")' in auth_router
    assert '@router.post("/register/supplier")' in auth_router
    assert '@router.post("/register/agent")' in auth_router
    assert '"customer"' in auth_router
    assert '"supplier"' in auth_router
    assert '"agent-reseller"' in auth_router


def test_auth_router_exposes_spec_session_routes():
    backend_dir = Path(__file__).resolve().parents[1]
    auth_router = (backend_dir / "app" / "routers" / "auth.py").read_text(encoding="utf-8")

    assert '@router.post("/refresh")' in auth_router
    assert '@router.post("/refresh-token")' in auth_router
    assert '@router.post("/logout")' in auth_router
    assert 'force_logout_user(db, current_user' in auth_router


def test_main_exposes_spec_admin_rbac_routes():
    backend_dir = Path(__file__).resolve().parents[1]
    main_py = (backend_dir / "app" / "main.py").read_text(encoding="utf-8")

    assert 'app.include_router(roles_router, prefix="/api")' in main_py
    assert 'app.include_router(roles_router, prefix="/api/admin")' in main_py
    assert 'app.include_router(permissions_router, prefix="/api")' in main_py
    assert 'app.include_router(permissions_router, prefix="/api/admin")' in main_py


def test_verification_workflow_status_contract_exists():
    backend_dir = Path(__file__).resolve().parents[1]
    operations = (backend_dir / "app" / "utils" / "operations.py").read_text(encoding="utf-8")

    for status in [
        "draft",
        "email_verification_pending",
        "profile_incomplete",
        "documents_pending",
        "admin_review_pending",
        "partially_approved",
        "approved_live",
        "rejected",
        "suspended",
        "blocked",
    ]:
        assert status in operations

    for status in ["expired", "reupload_required"]:
        assert status in operations


def test_supplier_agent_verification_api_contract_exists():
    backend_dir = Path(__file__).resolve().parents[1]
    supplier_router = (backend_dir / "app" / "routers" / "suppliers.py").read_text(encoding="utf-8")
    agent_router = (backend_dir / "app" / "routers" / "agents.py").read_text(encoding="utf-8")

    for route in ["/register", "/verify-email", "/submit-verification", "/pending"]:
        assert route in supplier_router
        assert route in agent_router

    for route in ["/{supplier_id}/approve", "/{supplier_id}/reject", "/{supplier_id}/request-reupload"]:
        assert route in supplier_router

    for route in ["/{agent_id}/approve", "/{agent_id}/reject", "/{agent_id}/discount", "/{agent_id}/request-correction"]:
        assert route in agent_router


def test_email_verification_moves_portal_profiles_forward():
    backend_dir = Path(__file__).resolve().parents[1]
    auth_service = (backend_dir / "app" / "services" / "auth.py").read_text(encoding="utf-8")

    assert "profile_incomplete" in auth_service
    assert "email_verification_pending" in auth_service
    assert "Supplier.user_id == user.id" in auth_service
    assert "Agent.user_id == user.id" in auth_service
