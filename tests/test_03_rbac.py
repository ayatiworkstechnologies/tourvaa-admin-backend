"""Module 03 - RBAC / Roles / Permissions"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique, unique_phone, create_active_account, login_with_retry


def _register_and_login_customer():
    email = f"{unique('rbac_cust')}@example.com"
    password = "Cust@1234"
    # A customer role carries none of the admin-module permissions
    # (view-users/view-roles/view-permissions) - this proves enforcement
    # actually denies, not just that the super-admin path is wired up.
    create_active_account("customer", "CUSTOMER", "RBAC Denial Test Customer", email, unique_phone(), password)
    login = login_with_retry(email, password)
    assert login.status_code == 200, login.text
    token = login.json().get("data", {}).get("access_token")
    assert token, login.text
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def limited_headers():
    return _register_and_login_customer()


def test_users_list_denied_for_unprivileged_role(limited_headers):
    resp = requests.get(f"{BASE_URL}/users/", headers=limited_headers, timeout=10)
    assert resp.status_code == 403, resp.text


def test_roles_list_denied_for_unprivileged_role(limited_headers):
    resp = requests.get(f"{BASE_URL}/roles/", headers=limited_headers, timeout=10)
    assert resp.status_code == 403, resp.text


def test_permissions_list_denied_for_unprivileged_role(limited_headers):
    resp = requests.get(f"{BASE_URL}/permissions/", headers=limited_headers, timeout=10)
    assert resp.status_code == 403, resp.text


def test_roles_list_loads(headers):
    resp = requests.get(f"{BASE_URL}/roles/", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_roles_list_is_array(headers):
    resp = requests.get(f"{BASE_URL}/roles/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list)


def test_permissions_list_loads(headers):
    resp = requests.get(f"{BASE_URL}/permissions/", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_permissions_list_not_empty(headers):
    resp = requests.get(f"{BASE_URL}/permissions/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert len(items) > 0, "Permissions list should not be empty"


def test_modules_list_loads(headers):
    resp = requests.get(f"{BASE_URL}/modules/", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_me_returns_permissions(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/me", headers=headers, timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    body = data.get("data", data)
    perms = body.get("permissions", [])
    assert len(perms) > 0, "Super admin should have permissions"


def test_auth_me_includes_roles(headers):
    resp = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
    body = resp.json()
    # /auth/me → {"data": {"user": {"roles": [...], "permissions": [...]}}}
    import json
    raw = json.dumps(body)
    has_role = '"roles"' in raw or '"role"' in raw or '"permissions"' in raw
    assert has_role, f"No role/permission data in /auth/me response"


def test_no_v1_permission_slugs(headers):
    resp = requests.get(f"{BASE_URL}/permissions/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    for p in items[:20]:
        slug = p.get("slug", "")
        assert "/v1/" not in slug, f"Permission slug should not contain /v1/: {slug}"


def test_roles_public_options():
    resp = requests.get(f"{BASE_URL}/roles/public/options", timeout=10)
    assert resp.status_code == 200


@skip_if_readonly()
def test_create_role(headers):
    import uuid
    suffix = uuid.uuid4().hex[:8]
    slug = f"test-role-{suffix}"
    resp = requests.post(f"{BASE_URL}/roles/", headers=headers, json={
        "name": f"Test Role {suffix}", "slug": slug, "description": "Test role"
    }, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    role = body.get("data", body)
    role_id = role.get("id")
    assert role_id
    # cleanup
    requests.delete(f"{BASE_URL}/roles/{role_id}", headers=headers, timeout=10)


@skip_if_readonly()
def test_create_permission(headers):
    import uuid
    suffix = uuid.uuid4().hex[:8]
    slug = f"test-perm-{suffix}"
    resp = requests.post(f"{BASE_URL}/permissions/", headers=headers, json={
        "name": f"test.permission.{suffix}", "slug": slug, "module": "test"
    }, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    perm = body.get("data", body)
    perm_id = perm.get("id")
    assert perm_id
    requests.delete(f"{BASE_URL}/permissions/{perm_id}", headers=headers, timeout=10)
