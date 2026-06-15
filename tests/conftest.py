import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("FRONTEND_URL", "http://testserver")
os.environ.setdefault("STORAGE_ROOT", "test-storage")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from app.modules.users.models import User
from app.security import hash_password


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


def create_role(db, slug="super-admin", name="Super Admin", is_system=False):
    role = Role(name=name, slug=slug, is_active=True, is_system=is_system)
    db.add(role)
    db.flush()
    return role


def create_permission(db, slug, module="users", action="get", is_system=False):
    permission = Permission(
        name=slug.replace("-", " ").title(),
        slug=slug,
        module=module,
        action=action,
        is_active=True,
        is_system=is_system,
    )
    db.add(permission)
    db.flush()
    return permission


def attach_permissions(db, role, permission_slugs):
    for slug in permission_slugs:
        action = "get"
        if slug.startswith("create-"):
            action = "post"
        elif slug.startswith("update-"):
            action = "put"
        elif slug.startswith("delete-"):
            action = "delete"

        permission = create_permission(db, slug, module=slug.split("-", 1)[-1], action=action)
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))


def create_user(
    db,
    *,
    email="admin@tourvaa.com",
    password="Password@123",
    role=None,
    is_active=True,
    approval_status="approved",
):
    user = User(
        name="Admin User",
        email=email.lower(),
        phone="",
        profile_image="",
        address="",
        country="",
        state="",
        city="",
        pincode="",
        password=hash_password(password),
        role_id=role.id if role else None,
        is_active=is_active,
        approval_status=approval_status,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def admin_setup(db):
    role = create_role(db, is_system=True)
    attach_permissions(
        db,
        role,
        [
            "view-dashboard",
            "view-users",
            "create-users",
            "update-users",
            "delete-users",
            "view-roles",
            "update-roles",
            "delete-roles",
        ],
    )
    user = create_user(db, role=role)
    db.commit()
    return user


@pytest.fixture
def admin_token(client, admin_setup):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@tourvaa.com", "password": "Password@123"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]
