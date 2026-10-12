from fastapi import HTTPException
from jose import jwt
import pytest

from app.auth.security import (
    create_token,
    decode_auth_token,
    get_auth_domain_for_role,
    get_portal_for_role,
)
from app.config import settings


def test_admin_and_normal_roles_use_separate_authentication_domains(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_JWT_SECRET_KEY", "a" * 64)
    monkeypatch.setattr(settings, "NORMAL_JWT_SECRET_KEY", "n" * 64)

    admin_token = create_token({"user_id": 1}, portal="admin")
    normal_token = create_token({"user_id": 2}, portal="customer")

    assert decode_auth_token(admin_token)["auth_domain"] == "admin"
    assert decode_auth_token(normal_token)["auth_domain"] == "normal"
    assert jwt.decode(admin_token, "a" * 64, algorithms=[settings.JWT_ALGORITHM])["portal"] == "admin"
    with pytest.raises(Exception):
        jwt.decode(admin_token, "n" * 64, algorithms=[settings.JWT_ALGORITHM])


@pytest.mark.parametrize("role", ["super-admin", "admin", "sub-admin"])
def test_back_office_roles_share_admin_authentication(role):
    assert get_auth_domain_for_role(role) == "admin"


@pytest.mark.parametrize("role", ["customer", "agent-reseller", "supplier", "affiliate"])
def test_customer_supplier_agent_and_affiliate_share_normal_authentication(role):
    assert get_auth_domain_for_role(role) == "normal"


def test_unknown_role_cannot_fall_back_to_privileged_admin_authentication():
    assert get_auth_domain_for_role("future-portal-role") == "normal"
    assert get_portal_for_role("future-portal-role") == "portal"


def test_token_with_missing_domain_claim_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_JWT_SECRET_KEY", "a" * 64)
    monkeypatch.setattr(settings, "NORMAL_JWT_SECRET_KEY", "n" * 64)
    token = jwt.encode({"user_id": 1}, "a" * 64, algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(HTTPException) as exc:
        decode_auth_token(token)

    assert exc.value.status_code == 401
