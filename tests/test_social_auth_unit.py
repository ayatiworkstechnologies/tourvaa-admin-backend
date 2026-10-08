from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.routers.social_auth import router
from app.auth.security import decode_auth_token


class _Db:
    def __init__(self, rows):
        self.rows = rows
        self.name = ""

    def query(self, *_args):
        return self

    def filter(self, expression):
        self.name = expression.right.value
        return self

    def first(self):
        return self.rows.get(self.name)


def _client(rows) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: _Db(rows)
    return TestClient(app)


def _provider(name: str, enabled: bool = True):
    return SimpleNamespace(
        api_name=f"oauth_{name}", api_key=f"{name}-client-id",
        api_secret=f"{name}-client-secret", is_enabled=enabled,
    )


def test_provider_status_reports_only_enabled_configured_providers(monkeypatch):
    monkeypatch.setattr("app.routers.social_auth.decrypt_secret", lambda value: value)
    response = _client({
        "oauth_google": _provider("google"),
        "oauth_facebook": _provider("facebook", enabled=False),
        "oauth_apple": _provider("apple"),
    }).get("/api/auth/oauth/providers")

    assert response.status_code == 200
    assert response.json()["data"] == {"google": True, "facebook": False, "apple": True}


def test_facebook_start_uses_signed_state_and_same_origin_callback(monkeypatch):
    monkeypatch.setattr("app.routers.social_auth.decrypt_secret", lambda value: value)
    monkeypatch.setattr("app.routers.social_auth.settings.FRONTEND_URL", "https://tourvaa.example")

    response = _client({"oauth_facebook": _provider("facebook")}).get(
        "/api/auth/oauth/facebook/start", params={"redirect": "/customer/dashboard"}, follow_redirects=False
    )

    assert response.status_code == 307
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["client_id"] == ["facebook-client-id"]
    assert query["redirect_uri"] == ["https://tourvaa.example/api/auth/oauth/facebook/callback"]
    assert query["state"]
    state_payload = decode_auth_token(query["state"][0])
    assert state_payload["auth_domain"] == "normal"
    assert state_payload["token_type"] == "oauth_state"


def test_social_callback_rejects_wrong_provider_state(monkeypatch):
    monkeypatch.setattr("app.routers.social_auth.settings.FRONTEND_URL", "https://tourvaa.example")
    response = _client({}).get(
        "/api/auth/oauth/facebook/callback", params={"code": "code", "state": "not-a-jwt"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "https://tourvaa.example/login?oauth_error=facebook_invalid_state"


def test_social_router_rejects_google_to_keep_its_dedicated_flow():
    response = _client({}).get("/api/auth/oauth/google/start", follow_redirects=False)

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown social provider"}
