from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.routers.google_auth import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_google_login_redirects_with_configured_oauth_parameters(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "new-client-id")
    monkeypatch.setattr(
        settings,
        "GOOGLE_REDIRECT_URI",
        "https://tourvaaapi.vercel.app/api/auth/google/callback",
    )

    response = _client().get("/api/auth/google", follow_redirects=False)

    assert response.status_code == 307
    parsed = urlparse(response.headers["location"])
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/v2/auth"
    query = parse_qs(parsed.query)
    assert query == {
        "client_id": ["new-client-id"],
        "redirect_uri": ["https://tourvaaapi.vercel.app/api/auth/google/callback"],
        "response_type": ["code"],
        "scope": ["openid email profile"],
        "access_type": ["offline"],
        "prompt": ["consent"],
        "state": [query["state"][0]],
    }


def test_google_login_fails_cleanly_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", "")

    response = _client().get("/api/auth/google", follow_redirects=False)

    assert response.status_code == 503
    assert response.json() == {"detail": "Google authentication is not configured"}


def test_google_callback_rejects_missing_state_without_exposing_code(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:3000")

    response = _client().get(
        "/api/auth/google/callback",
        params={"code": "test-code"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "http://localhost:3000/login?oauth_error=google_invalid_callback"
    )
    assert "test-code" not in response.headers["location"]


def test_google_routes_are_visible_in_openapi():
    paths = _client().get("/openapi.json").json()["paths"]

    assert "/api/auth/google" in paths
    assert "/api/auth/google/callback" in paths
