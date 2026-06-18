"""Module 01 — Core / Health"""
import requests
from tests.conftest import BASE_URL


def test_health_returns_200():
    resp = requests.get(f"{BASE_URL}/health", timeout=10)
    assert resp.status_code == 200


def test_health_response_body():
    resp = requests.get(f"{BASE_URL}/health", timeout=10)
    body = resp.json()
    assert body.get("status") == "success"


def test_openapi_loads():
    resp = requests.get("http://127.0.0.1:8000/openapi.json", timeout=10)
    assert resp.status_code == 200


def test_openapi_has_paths():
    resp = requests.get("http://127.0.0.1:8000/openapi.json", timeout=10)
    data = resp.json()
    paths = data.get("paths", {})
    assert len(paths) > 0, "OpenAPI must have routes"


def test_openapi_no_v1_paths():
    resp = requests.get("http://127.0.0.1:8000/openapi.json", timeout=10)
    data = resp.json()
    v1_paths = [p for p in data.get("paths", {}) if "/v1/" in p or p.startswith("/v1")]
    assert v1_paths == [], f"Unexpected /api/v1 paths found: {v1_paths}"


def test_root_redirects_or_responds():
    resp = requests.get("http://127.0.0.1:8000/", timeout=10, allow_redirects=True)
    assert resp.status_code in (200, 307, 308, 404)
