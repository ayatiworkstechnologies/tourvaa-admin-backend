from fastapi import HTTPException
from jose import jwt
import pytest

from app.auth.security import (
    create_token,
    decode_auth_token,
    get_auth_domain_for_role,
)
from app.config import settings


def test_staff_and_portal_roles_use_separate_authentication_domains(monkeypatch):
    monkeypatch.setattr(settings, "STAFF_JWT_SECRET_KEY", "s" * 64)
    monkeypatch.setattr(settings, "PORTAL_JWT_SECRET_KEY", "p" * 64)

    staff_token = create_token({"user_id": 1}, portal="admin")
    portal_token = create_token({"user_id": 2}, portal="customer")

    assert decode_auth_token(staff_token)["auth_domain"] == "staff"
    assert decode_auth_token(portal_token)["auth_domain"] == "portal"
    assert jwt.decode(staff_token, "s" * 64, algorithms=[settings.JWT_ALGORITHM])["portal"] == "admin"
    with pytest.raises(Exception):
        jwt.decode(staff_token, "p" * 64, algorithms=[settings.JWT_ALGORITHM])


@pytest.mark.parametrize("role", ["super-admin", "admin", "sub-admin"])
def test_back_office_roles_share_staff_authentication(role):
    assert get_auth_domain_for_role(role) == "staff"


@pytest.mark.parametrize("role", ["customer", "agent-reseller", "supplier", "affiliate"])
def test_portal_roles_share_portal_authentication(role):
    assert get_auth_domain_for_role(role) == "portal"


def test_token_with_missing_domain_claim_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "STAFF_JWT_SECRET_KEY", "s" * 64)
    monkeypatch.setattr(settings, "PORTAL_JWT_SECRET_KEY", "p" * 64)
    token = jwt.encode({"user_id": 1}, "s" * 64, algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(HTTPException) as exc:
        decode_auth_token(token)

    assert exc.value.status_code == 401
