import json
import os
import time
import urllib.error
import urllib.request

import pytest


API_URL = os.getenv("TOURVAA_API_URL", "http://127.0.0.1:8000/api").rstrip("/")
ADMIN_EMAIL = os.getenv("TOURVAA_TEST_EMAIL", "admin@tourvaa.com")
ADMIN_PASSWORD = os.getenv("TOURVAA_TEST_PASSWORD", "Admin@123")
WRITE_TESTS = os.getenv("TOURVAA_WRITE_TESTS", "").lower() in {"1", "true", "yes"}


class ApiClient:
    def __init__(self, base_url, token=None, credentials=None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.credentials = credentials

    def login(self):
        if not self.credentials:
            return
        anonymous = ApiClient(self.base_url)
        payload = anonymous.post("/auth/login", self.credentials)
        token = payload.get("data", {}).get("access_token")
        assert token, payload
        self.token = token

    def request(self, method, path, body=None, expected=(200,)):
        status = None
        raw = ""
        did_relogin = False
        for attempt in range(4):
            data = None
            headers = {"Accept": "application/json"}
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            request = urllib.request.Request(
                f"{self.base_url}{path}",
                data=data,
                headers=headers,
                method=method,
            )

            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    status = response.status
                    raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                status = exc.code
                raw = exc.read().decode("utf-8", errors="replace")
                if (
                    status == 401
                    and not did_relogin
                    and self.credentials
                    and path != "/auth/login"
                    and "Token has expired" in raw
                ):
                    did_relogin = True
                    self.login()
                    continue
                break
            except (ConnectionResetError, urllib.error.URLError) as exc:
                if attempt == 2:
                    reason = getattr(exc, "reason", exc)
                    pytest.fail(f"Backend API is not reachable at {self.base_url}: {reason}")
                time.sleep(1)

        assert status in expected, f"{method} {path} expected {expected}, got {status}: {raw[:500]}"
        return json.loads(raw) if raw else {}

    def get(self, path, expected=(200,)):
        return self.request("GET", path, expected=expected)

    def post(self, path, body=None, expected=(200,)):
        return self.request("POST", path, body=body, expected=expected)

    def put(self, path, body=None, expected=(200,)):
        return self.request("PUT", path, body=body, expected=expected)

    def patch(self, path, body=None, expected=(200,)):
        return self.request("PATCH", path, body=body, expected=expected)


def unique(prefix):
    return f"{prefix} {int(time.time() * 1000)}"


def data_id(payload):
    data = payload.get("data")
    assert isinstance(data, dict), payload
    assert isinstance(data.get("id"), int), payload
    return data["id"]


@pytest.fixture(scope="session")
def api_client():
    credentials = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "client_type": "web",
    }
    client = ApiClient(API_URL)
    payload = client.post("/auth/login", credentials)
    token = payload.get("data", {}).get("access_token")
    assert token, payload
    return ApiClient(API_URL, token, credentials=credentials)


@pytest.fixture
def require_write_tests():
    if not WRITE_TESTS:
        pytest.skip("Set TOURVAA_WRITE_TESTS=1 to run write/action API tests.")
