"""Module 03 - RBAC / Roles / Permissions"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique


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
