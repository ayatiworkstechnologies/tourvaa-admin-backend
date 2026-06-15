from sqlalchemy.orm import Session

from app.config import settings
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from app.modules.users.models import User
from app.security import hash_password


DEFAULT_ROLES = [
    {"name": "Super Admin", "slug": "super-admin"},
    {"name": "Admin", "slug": "admin"},
    {"name": "Sub Admin", "slug": "sub-admin"},
    {"name": "Supplier", "slug": "supplier"},
    {"name": "Agent / Reseller", "slug": "agent-reseller"},
    {"name": "Customer", "slug": "customer"},
]

MODULES = [
    ("dashboard", "Dashboard"),
    ("users", "Users"),
    ("roles", "Roles"),
    ("permissions", "Permissions"),
    ("suppliers", "Suppliers"),
    ("agents", "Agents"),
    ("resellers", "Resellers"),
    ("customers", "Customers"),
    ("tours", "Tours"),
    ("bookings", "Bookings"),
    ("payments", "Payments"),
    ("reports", "Reports"),
    ("email", "Email Templates"),
    ("settings", "Settings"),
    ("profile", "Profile"),
]

ACTION_LABELS = {
    "get": "View",
    "post": "Create",
    "put": "Update",
    "delete": "Delete",
}


def permission_slug(action: str, module: str):
    if action == "get":
        return f"view-{module}"

    if action == "post":
        return f"create-{module}"

    if action == "put":
        return f"update-{module}"

    return f"delete-{module}"


DEFAULT_PERMISSIONS = [
    {
        "name": f"{label} {module_label}",
        "slug": permission_slug(action, module),
        "module": module,
        "action": action,
    }
    for module, module_label in MODULES
    for action, label in ACTION_LABELS.items()
]


def assign_if_missing(db: Session, role: Role, permission: Permission):
    exists = (
        db.query(RolePermission)
        .filter(RolePermission.role_id == role.id)
        .filter(RolePermission.permission_id == permission.id)
        .first()
    )

    if not exists:
        db.add(
            RolePermission(
                role_id=role.id,
                permission_id=permission.id,
            )
        )


def seed_super_admin_user(db: Session, role: Role | None):
    if not role:
        return

    email = settings.SUPER_ADMIN_EMAIL.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        user = User(
            name=settings.SUPER_ADMIN_NAME.strip() or "Super Admin",
            email=email,
            phone="",
            profile_image="",
            address="",
            country="",
            state="",
            city="",
            pincode="",
            password=hash_password(settings.SUPER_ADMIN_PASSWORD),
            role_id=role.id,
            is_active=True,
            approval_status="approved",
        )
        db.add(user)
        db.flush()
        return

    user.name = user.name or settings.SUPER_ADMIN_NAME.strip() or "Super Admin"
    user.role_id = role.id
    user.is_active = True
    user.approval_status = "approved"

    if settings.SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP:
        user.password = hash_password(settings.SUPER_ADMIN_PASSWORD)


def seed_default_roles_and_permissions(db: Session):
    roles_by_slug = {}

    for role_data in DEFAULT_ROLES:
        role = db.query(Role).filter(Role.slug == role_data["slug"]).first()

        if not role:
            role = Role(**role_data, is_active=True, is_system=True)
            db.add(role)
            db.flush()
        else:
            role.is_system = True

        roles_by_slug[role.slug] = role

    permissions = []

    for permission_data in DEFAULT_PERMISSIONS:
        permission = (
            db.query(Permission)
            .filter(Permission.slug == permission_data["slug"])
            .first()
        )

        if not permission:
            permission = Permission(**permission_data, is_active=True, is_system=True)
            db.add(permission)
            db.flush()
        else:
            permission.name = permission_data["name"]
            permission.module = permission_data["module"]
            permission.action = permission_data["action"]
            permission.is_system = True

        permissions.append(permission)

    permissions_by_slug = {permission.slug: permission for permission in permissions}

    super_admin = roles_by_slug.get("super-admin")
    admin = roles_by_slug.get("admin")
    sub_admin = roles_by_slug.get("sub-admin")
    supplier = roles_by_slug.get("supplier")
    agent_reseller = roles_by_slug.get("agent-reseller")
    customer = roles_by_slug.get("customer")

    if super_admin:
        for permission in permissions:
            assign_if_missing(db, super_admin, permission)

        seed_super_admin_user(db, super_admin)

    default_role_permissions = {
        admin: [
            "view-dashboard",
            "view-users",
            "create-users",
            "update-users",
            "delete-users",
            "view-roles",
            "create-roles",
            "update-roles",
            "delete-roles",
            "view-permissions",
            "create-permissions",
            "update-permissions",
            "delete-permissions",
            "view-customers",
            "create-customers",
            "update-customers",
            "view-tours",
            "create-tours",
            "update-tours",
            "view-bookings",
            "create-bookings",
            "update-bookings",
            "view-payments",
            "view-reports",
            "view-email",
            "create-email",
            "update-email",
            "view-settings",
            "update-settings",
            "view-profile",
            "update-profile",
        ],
        sub_admin: [
            "view-dashboard",
            "view-users",
            "create-users",
            "update-users",
            "view-suppliers",
            "create-suppliers",
            "update-suppliers",
            "view-agents",
            "create-agents",
            "update-agents",
            "view-resellers",
            "create-resellers",
            "update-resellers",
            "view-customers",
            "create-customers",
            "update-customers",
            "view-tours",
            "create-tours",
            "update-tours",
            "view-bookings",
            "create-bookings",
            "update-bookings",
            "view-payments",
            "view-reports",
            "view-email",
            "create-email",
            "update-email",
            "view-settings",
            "view-profile",
            "update-profile",
        ],
        supplier: [
            "view-dashboard",
            "view-suppliers",
            "update-suppliers",
            "view-tours",
            "create-tours",
            "update-tours",
            "view-bookings",
            "update-bookings",
            "view-payments",
            "view-reports",
            "view-profile",
            "update-profile",
        ],
        agent_reseller: [
            "view-dashboard",
            "view-agents",
            "update-agents",
            "view-resellers",
            "update-resellers",
            "view-customers",
            "create-customers",
            "update-customers",
            "view-tours",
            "view-bookings",
            "create-bookings",
            "update-bookings",
            "view-payments",
            "view-reports",
            "view-profile",
            "update-profile",
        ],
        customer: [
            "view-dashboard",
            "view-tours",
            "view-bookings",
            "create-bookings",
            "view-profile",
            "update-profile",
        ],
    }

    for role, permission_slugs in default_role_permissions.items():
        if not role:
            continue

        for slug in permission_slugs:
            permission = permissions_by_slug.get(slug)

            if permission:
                assign_if_missing(db, role, permission)

    db.commit()
