from app.modules.roles.models import Role
from app.modules.users.models import User
from app.security import hash_password


def test_login_success_and_failure(client, admin_setup):
    success = client.post(
        "/api/auth/login",
        json={"email": "ADMIN@TOURVAA.COM", "password": "Password@123"},
    )
    assert success.status_code == 200
    assert success.json()["data"]["access_token"]

    failure = client.post(
        "/api/auth/login",
        json={"email": "admin@tourvaa.com", "password": "wrong-password"},
    )
    assert failure.status_code == 401


def test_inactive_pending_rejected_user_login(client, db):
    role = Role(name="Customer", slug="customer", is_active=True)
    db.add(role)
    db.flush()

    for email, is_active, status in [
        ("inactive@example.com", False, "approved"),
        ("pending@example.com", True, "pending"),
        ("rejected@example.com", False, "rejected"),
    ]:
        db.add(
            User(
                name=email,
                email=email,
                phone="",
                profile_image="",
                address="",
                country="",
                state="",
                city="",
                pincode="",
                password=hash_password("Password@123"),
                role_id=role.id,
                is_active=is_active,
                approval_status=status,
            )
        )
    db.commit()

    for email in ["inactive@example.com", "pending@example.com", "rejected@example.com"]:
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "Password@123"},
        )
        assert response.status_code == 403


def test_forgot_password_uses_generic_response(client):
    response = client.post(
        "/api/auth/forgot-password",
        json={"email": "missing@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "If an eligible account exists, a reset link has been sent."


def test_upload_requires_auth(client):
    response = client.post(
        "/api/uploads/profile-image",
        files={"file": ("avatar.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "image/png")},
    )
    assert response.status_code == 401


def test_dashboard_blocks_inactive_user(client, db, admin_setup):
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@tourvaa.com", "password": "Password@123"},
    )
    token = login.json()["data"]["access_token"]

    user = db.query(User).filter(User.email == "admin@tourvaa.com").first()
    user.is_active = False
    db.commit()

    response = client.get("/api/dashboard/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_permission_assignment_invalid_ids(client, admin_token):
    response = client.post(
        "/api/roles/1/permissions",
        json={"permission_ids": [9999]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["invalid_ids"] == [9999]


def test_protected_role_cannot_be_deleted(client, admin_token):
    response = client.delete(
        "/api/roles/1",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400


def test_last_super_admin_cannot_be_disabled_or_deleted(client, admin_token):
    disable = client.put(
        "/api/users/1",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert disable.status_code == 400

    delete = client.delete(
        "/api/users/1",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete.status_code == 400


def test_token_version_invalidates_old_token(client, db, admin_setup):
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@tourvaa.com", "password": "Password@123"},
    )
    token = login.json()["data"]["access_token"]

    user = db.query(User).filter(User.email == "admin@tourvaa.com").first()
    user.token_version += 1
    db.commit()

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
