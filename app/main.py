from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.database import Base, SessionLocal, engine
from app.config import settings

# Import models before create_all
from app.modules.roles.models import Role
from app.modules.permissions.models import Permission, RolePermission
from app.modules.users.models import User
from app.modules.settings.models import AppSetting
from app.modules.email_templates.models import EmailTemplate
from app.seed import seed_default_roles_and_permissions
from app.modules.email_templates.service import seed_email_templates

from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router
from app.modules.roles.router import router as roles_router
from app.modules.permissions.router import router as permissions_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.profile.router import router as profile_router
from app.modules.settings.router import router as settings_router
from app.modules.email_templates.router import router as email_templates_router
from app.modules.uploads.router import router as uploads_router
from app.modules.client.router import router as client_router

Base.metadata.create_all(bind=engine)


def sync_existing_schema():
    inspector = inspect(engine)

    if "users" not in inspector.get_table_names():
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}

    if "approval_status" not in user_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN approval_status VARCHAR(20) DEFAULT 'approved' NOT NULL"
                )
            )

    user_profile_columns = {
        "phone": "ALTER TABLE users ADD COLUMN phone VARCHAR(30) DEFAULT '' NOT NULL",
        "profile_image": "ALTER TABLE users ADD COLUMN profile_image VARCHAR(255) DEFAULT '' NOT NULL",
        "address": "ALTER TABLE users ADD COLUMN address VARCHAR(255) DEFAULT '' NOT NULL",
        "country": "ALTER TABLE users ADD COLUMN country VARCHAR(100) DEFAULT '' NOT NULL",
        "state": "ALTER TABLE users ADD COLUMN state VARCHAR(100) DEFAULT '' NOT NULL",
        "city": "ALTER TABLE users ADD COLUMN city VARCHAR(100) DEFAULT '' NOT NULL",
        "pincode": "ALTER TABLE users ADD COLUMN pincode VARCHAR(20) DEFAULT '' NOT NULL",
    }

    for column_name, alter_statement in user_profile_columns.items():
        if column_name not in user_columns:
            with engine.begin() as connection:
                connection.execute(text(alter_statement))

    if "reset_password_token" not in user_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN reset_password_token VARCHAR(255)")
            )

    if "reset_password_expires_at" not in user_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN reset_password_expires_at DATETIME")
            )

    if "permissions" in inspector.get_table_names():
        permission_columns = {
            column["name"] for column in inspector.get_columns("permissions")
        }

        if "action" not in permission_columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE permissions "
                        "ADD COLUMN action VARCHAR(20) DEFAULT 'get' NOT NULL"
                    )
                )


sync_existing_schema()

db = SessionLocal()
try:
    seed_default_roles_and_permissions(db)
    seed_email_templates(db)
finally:
    db.close()

app = FastAPI(
    title="Tourvaa Backend",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Client-Type", "X-Client-Version", "X-Device-Id"],
)

Path("storage/uploads/profile-images").mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(roles_router, prefix="/api")
app.include_router(permissions_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(profile_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(email_templates_router, prefix="/api")
app.include_router(uploads_router, prefix="/api")
app.include_router(client_router, prefix="/api")


@app.get("/")
def home():
    return {
        "status": "success",
        "message": "Tourvaa Backend Running"
    }


@app.get("/api/health")
def health():
    return {
        "status": "success",
        "message": "API working fine"
    }
