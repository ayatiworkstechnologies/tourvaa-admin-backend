"""Live HTTP regression coverage for single-device logout.

The test is write-gated because it creates an isolated active customer account.
It proves that logging out one bearer-token session revokes that token without
invalidating another session belonging to the same user.
"""

import requests

from tests.conftest import (
    BASE_URL,
    auth_headers,
    create_active_account,
    login_with_retry,
    skip_if_readonly,
    unique,
    unique_phone,
)


@skip_if_readonly()
def test_logout_revokes_only_the_current_http_session():
    password = "LogoutHttp@123"
    email = f"{unique('logout-http')}@example.com"
    create_active_account("customer", "CUSTOMER", "Logout HTTP", email, unique_phone(), password)

    first = login_with_retry(email, password)
    second = login_with_retry(email, password)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    first_token = first.json()["data"]["access_token"]
    second_token = second.json()["data"]["access_token"]

    logout = requests.post(f"{BASE_URL}/auth/logout", headers=auth_headers(first_token), timeout=10)
    assert logout.status_code == 200, logout.text

    first_after = requests.get(f"{BASE_URL}/dashboard/me", headers=auth_headers(first_token), timeout=10)
    second_after = requests.get(f"{BASE_URL}/dashboard/me", headers=auth_headers(second_token), timeout=10)
    assert first_after.status_code == 401, first_after.text
    assert second_after.status_code == 200, second_after.text
