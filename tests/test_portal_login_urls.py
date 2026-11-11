from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.auth import build_portal_login_url


@pytest.mark.parametrize(
    ("role_slug", "portal_path"),
    [
        ("customer", "/login"),
        ("agent-reseller", "/agent-portal/login"),
        ("supplier", "/supplier-portal/login"),
        ("affiliate", "/affiliate-portal/login"),
        ("admin", "/admin/login"),
    ],
)
def test_role_email_login_url_targets_the_correct_portal(monkeypatch, role_slug, portal_path):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://tourvaa.example")
    user = SimpleNamespace(role=SimpleNamespace(slug=role_slug))

    assert build_portal_login_url(user) == f"https://tourvaa.example{portal_path}"


def test_supplier_role_never_uses_the_traveller_login(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://tourvaa.example")
    supplier = SimpleNamespace(role=SimpleNamespace(slug="supplier"))

    login_url = build_portal_login_url(supplier)

    assert login_url.endswith("/supplier-portal/login")
    assert "/login?role=" not in login_url
