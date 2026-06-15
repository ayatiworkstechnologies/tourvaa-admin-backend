from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
import logging

from app.database import SessionLocal, engine
from app.config import get_storage_root, settings

from app.modules.roles.models import Role
from app.modules.admin_modules.models import AdminModule
from app.modules.permissions.models import Permission, RolePermission
from app.modules.users.models import User
from app.modules.settings.models import ApiSetting, AppSetting, PaymentSetting
from app.modules.email_templates.models import EmailTemplate
from app.modules.audit.models import AuditLog
from app.modules.customers.models import Customer, CustomerCommunication
from app.seed import seed_default_roles_and_permissions
from app.modules.email_templates.service import seed_email_templates

from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router
from app.modules.roles.router import router as roles_router
from app.modules.permissions.router import router as permissions_router
from app.modules.admin_modules.router import router as admin_modules_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.profile.router import router as profile_router
from app.modules.settings.router import router as settings_router
from app.modules.email_templates.router import router as email_templates_router
from app.modules.uploads.router import router as uploads_router
from app.modules.client.router import router as client_router
from app.modules.customers.router import router as customers_router

logger = logging.getLogger(__name__)


def schema_is_ready():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required_tables = {
        "roles",
        "permissions",
        "role_permissions",
        "users",
        "email_templates",
        "app_settings",
        "payment_settings",
        "api_settings",
        "audit_logs",
        "admin_modules",
        "user_roles",
        "customers",
        "customer_communications",
    }

    if not required_tables.issubset(tables):
        return False

    required_columns = {
        "roles": {"is_system"},
        "permissions": {"action", "is_system"},
        "users": {
            "approval_status",
            "reset_password_token",
            "reset_password_expires_at",
            "token_version",
        },
    }

    for table_name, column_names in required_columns.items():
        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        if not column_names.issubset(existing_columns):
            return False

    return True


if schema_is_ready():
    db = SessionLocal()
    try:
        seed_default_roles_and_permissions(db)
        seed_email_templates(db)
    finally:
        db.close()
else:
    logger.warning(
        "Database schema is not ready; skipping seed. Run `python -m alembic upgrade head` before starting the API."
    )

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

storage_root = get_storage_root()
storage_root.joinpath("uploads", "profile-images").mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_root)), name="storage")

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(roles_router, prefix="/api")
app.include_router(permissions_router, prefix="/api")
app.include_router(admin_modules_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(profile_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(email_templates_router, prefix="/api")
app.include_router(uploads_router, prefix="/api")
app.include_router(client_router, prefix="/api")
app.include_router(customers_router, prefix="/api")

app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(roles_router, prefix="/api/v1")
app.include_router(permissions_router, prefix="/api/v1")
app.include_router(admin_modules_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(email_templates_router, prefix="/api/v1")
app.include_router(uploads_router, prefix="/api/v1")
app.include_router(client_router, prefix="/api/v1")
app.include_router(customers_router, prefix="/api/v1")


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
