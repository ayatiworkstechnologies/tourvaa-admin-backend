from app.modules.permissions.models import Permission, RolePermission
from app.modules.users.models import UserRole
from tests.conftest import create_permission, create_role, create_user


def test_assign_multiple_roles_to_user(client, db, admin_token):
    role_one = create_role(db, slug="support-staff", name="Support Staff")
    role_two = create_role(db, slug="finance-staff", name="Finance Staff")
    user = create_user(db, email="staff@tourvaa.com", role=role_one)
    db.commit()

    response = client.post(
        f"/api/users/{user.id}/roles",
        json={"role_ids": [role_one.id, role_two.id]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["role_id"] == role_one.id
    assert {role["slug"] for role in response.json()["data"]["roles"]} == {
        "support-staff",
        "finance-staff",
    }

    db.expire_all()
    assert db.query(UserRole).filter(UserRole.user_id == user.id).count() == 2


def test_permission_check_uses_secondary_role(client, db, admin_token):
    base_role = create_role(db, slug="base-role", name="Base Role")
    settings_role = create_role(db, slug="settings-role", name="Settings Role")
    permission = db.query(Permission).filter(Permission.slug == "view-settings").first()
    if not permission:
        permission = create_permission(db, "view-settings", module="settings")
    user = create_user(db, email="multi@tourvaa.com", role=base_role)
    db.add(RolePermission(role_id=settings_role.id, permission_id=permission.id))
    db.add(UserRole(user_id=user.id, role_id=base_role.id))
    db.add(UserRole(user_id=user.id, role_id=settings_role.id))
    db.commit()

    login = client.post(
        "/api/auth/login",
        json={"email": "multi@tourvaa.com", "password": "Password@123"},
    )
    assert login.status_code == 200

    response = client.get(
        "/api/settings/",
        headers={"Authorization": f"Bearer {login.json()['data']['access_token']}"},
    )

    assert response.status_code == 200
