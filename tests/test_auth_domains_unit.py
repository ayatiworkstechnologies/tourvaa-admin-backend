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


@pytest.mark.parametrize("role", ["super-admin", "admin", "sub-admin", "accountant", "finance-manager"])
def test_back_office_roles_share_admin_authentication(role):
    assert get_auth_domain_for_role(role) == "admin"


@pytest.mark.parametrize("role", ["customer", "agent-reseller", "supplier", "affiliate"])
def test_customer_supplier_agent_and_affiliate_share_normal_authentication(role):
    assert get_auth_domain_for_role(role) == "normal"


def test_custom_back_office_role_uses_permission_scoped_admin_shell():
    assert get_auth_domain_for_role("future-portal-role") == "admin"
    assert get_portal_for_role("future-portal-role") == "admin"


def test_token_with_missing_domain_claim_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_JWT_SECRET_KEY", "a" * 64)
    monkeypatch.setattr(settings, "NORMAL_JWT_SECRET_KEY", "n" * 64)
    token = jwt.encode({"user_id": 1}, "a" * 64, algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(HTTPException) as exc:
        decode_auth_token(token)

    assert exc.value.status_code == 401


def test_websocket_ticket_can_be_redeemed_without_redis(monkeypatch):
    from app.services import messaging_ws

    monkeypatch.setattr(messaging_ws, "get_redis_sync", lambda: None)
    store = messaging_ws._TicketStore()

    ticket = store.issue(42)

    assert store.redeem(ticket) == 42
