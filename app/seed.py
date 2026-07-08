from sqlalchemy.orm import Session

from app.config import settings
from app.models.admin_modules import AdminModule
from app.models.permissions import Permission, RolePermission
from app.models.roles import Role
from app.models.users import User, UserRole
from app.auth.security import hash_password


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
    ("affiliates", "Affiliates"),
    ("resellers", "Resellers"),
    ("customers", "Customers"),
    ("countries", "Countries"),
    ("cities", "Cities"),
    ("tours", "Tours"),
    ("categories", "Tour Categories"),
    ("subcategories", "Tour Sub-Categories"),
    ("bookings", "Bookings"),
    ("cancellations", "Cancellations"),
    ("payments", "Payments"),
    ("supplier_ledger", "Supplier Ledger"),
    ("reports", "Reports"),
    ("invoices", "Invoices"),
    ("notifications", "Notifications"),
    ("activity_logs", "Activity Logs"),
    ("sessions", "Sessions"),
    ("email", "Email Templates"),
    ("settings", "Settings"),
    ("website_cms", "Website CMS"),
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


# 27 modules x 4 HTTP actions = 108 base permissions
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

CUSTOMER_GRANULAR_PERMISSIONS = [
    {"name": "View Customers", "slug": "customers.view", "module": "customers", "action": "get"},
    {"name": "Create Customers", "slug": "customers.create", "module": "customers", "action": "post"},
    {"name": "Edit Customers", "slug": "customers.edit", "module": "customers", "action": "put"},
    {"name": "Block Customers", "slug": "customers.block", "module": "customers", "action": "put"},
    {"name": "Unblock Customers", "slug": "customers.unblock", "module": "customers", "action": "put"},
    {"name": "Reset Customer Password", "slug": "customers.reset_password", "module": "customers", "action": "post"},
    {"name": "View Customer Bookings", "slug": "customers.view_bookings", "module": "customers", "action": "get"},
    {"name": "View Customer Payments", "slug": "customers.view_payments", "module": "customers", "action": "get"},
    {"name": "View Customer Communications", "slug": "customers.view_communications", "module": "customers", "action": "get"},
    {"name": "Communicate With Customers", "slug": "customers.communicate", "module": "customers", "action": "post"},
    {"name": "Export Customers", "slug": "customers.export", "module": "customers", "action": "get"},
]

DEFAULT_PERMISSIONS.extend(CUSTOMER_GRANULAR_PERMISSIONS)

EMAIL_TEMPLATE_GRANULAR_PERMISSIONS = [
    {"name": "View Email Templates", "slug": "email_templates.view", "module": "email", "action": "get"},
    {"name": "Create Email Templates", "slug": "email_templates.create", "module": "email", "action": "post"},
    {"name": "Edit Email Templates", "slug": "email_templates.edit", "module": "email", "action": "put"},
    {"name": "Delete Email Templates", "slug": "email_templates.delete", "module": "email", "action": "delete"},
]

DEFAULT_PERMISSIONS.extend(EMAIL_TEMPLATE_GRANULAR_PERMISSIONS)

# Dashboard-only granular permissions -- no overlap with WEEK_11_15_PERMISSIONS slugs
DASHBOARD_PERMISSIONS = [
    {"name": "View Dashboard", "slug": "dashboard.view", "module": "dashboard", "action": "get"},
    {"name": "View Dashboard Summary", "slug": "dashboard.summary", "module": "dashboard", "action": "get"},
    {"name": "View Dashboard Charts", "slug": "dashboard.charts", "module": "dashboard", "action": "get"},
    {"name": "View Dashboard Activities", "slug": "dashboard.activities", "module": "dashboard", "action": "get"},
    {"name": "View Dashboard Alerts", "slug": "dashboard.alerts", "module": "dashboard", "action": "get"},
    {"name": "View Payment Summary", "slug": "payments.summary", "module": "payments", "action": "get"},
    {"name": "View Settings", "slug": "settings.view", "module": "settings", "action": "get"},
    {"name": "View Profile", "slug": "profile.view", "module": "profile", "action": "get"},
]

DEFAULT_PERMISSIONS.extend(DASHBOARD_PERMISSIONS)

# Operational / CMS / Geo module granular permissions
OPERATIONAL_PERMISSIONS = [
    ("suppliers", "Suppliers", [
        "view", "create", "edit", "approve", "reject", "partial_approve",
        "manage_markup", "request_commission", "approve_commission", "view_documents", "reset_password", "communicate", "export",
    ]),
    ("agents", "Agents", [
        "view", "create", "edit", "approve", "reject", "partial_approve",
        "manage_discount", "approve_discount", "view_documents", "reset_password", "communicate", "export",
    ]),
    ("affiliates", "Affiliates", [
        "view", "create", "approve", "reject", "manage_api_link", "view_documents", "export",
    ]),
    ("countries", "Countries", ["view", "create", "edit", "disable"]),
    ("cities", "Cities", ["view", "create", "edit", "disable"]),
    ("categories", "Categories", ["view", "create", "edit", "disable"]),
    ("subcategories", "Sub-Categories", ["view", "create", "edit", "disable"]),
    ("tours", "Tours", ["view", "create", "edit", "publish", "disable"]),
    ("supplier_ledger", "Supplier Ledger", ["view", "create_payout", "approve", "mark_paid", "export"]),
    ("website_cms", "Website CMS", ["view", "create", "edit", "delete"]),
]

# Booking lifecycle, financial, and system module granular permissions
WEEK_11_15_PERMISSIONS = [
    ("bookings", "Bookings", [
        "view", "create", "edit", "update_status", "assign_supplier",
        "cancel", "view_travellers", "view_payments", "view_history", "export",
    ]),
    ("cancellations", "Cancellations", ["view", "approve", "reject", "process_refund"]),
    ("payments", "Payments", [
        "view", "create", "edit", "capture", "void", "refund",
        "view_transactions", "export", "manage_settings",
    ]),
    ("invoices", "Invoices", ["view", "generate", "email", "download", "export"]),
    ("notifications", "Notifications", ["view", "manage", "retry"]),
    ("reports", "Reports", ["view", "admin", "supplier", "agent", "export"]),
    ("activity_logs", "Activity Logs", ["view", "export"]),
    ("sessions", "Sessions", ["view", "revoke", "force_logout"]),
]

for module, label, actions in WEEK_11_15_PERMISSIONS:
    for action in actions:
        DEFAULT_PERMISSIONS.append({
            "name": f"{action.replace('_', ' ').title()} {label}",
            "slug": f"{module}.{action}",
            "module": module,
            "action": action,
        })

for module, label, actions in OPERATIONAL_PERMISSIONS:
    for action in actions:
        DEFAULT_PERMISSIONS.append({
            "name": f"{action.replace('_', ' ').title()} {label}",
            "slug": f"{module}.{action}",
            "module": module,
            "action": action,
        })


def assign_if_missing(db: Session, role: Role, permission: Permission):
    exists = (
        db.query(RolePermission)
        .filter(RolePermission.role_id == role.id)
        .filter(RolePermission.permission_id == permission.id)
        .first()
    )
    if not exists:
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))


def assign_user_role_if_missing(db: Session, user: User, role: Role):
    exists = (
        db.query(UserRole)
        .filter(UserRole.user_id == user.id)
        .filter(UserRole.role_id == role.id)
        .first()
    )
    if not exists:
        db.add(UserRole(user_id=user.id, role_id=role.id))


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
        assign_user_role_if_missing(db, user, role)
        return

    user.name = user.name or settings.SUPER_ADMIN_NAME.strip() or "Super Admin"
    user.role_id = role.id
    assign_user_role_if_missing(db, user, role)
    user.is_active = True
    user.approval_status = "approved"

    if settings.SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP:
        user.password = hash_password(settings.SUPER_ADMIN_PASSWORD)



def seed_default_roles_and_permissions(db: Session):
    for slug, name in MODULES:
        admin_module = db.query(AdminModule).filter(AdminModule.slug == slug).first()
        if not admin_module:
            db.add(AdminModule(
                name=name,
                slug=slug,
                description=f"{name} admin module",
                is_active=True,
                is_system=True,
            ))
        else:
            admin_module.name = name
            admin_module.is_system = True

    db.flush()

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

    permissions_by_slug = {p.slug: p for p in permissions}

    super_admin = roles_by_slug.get("super-admin")
    admin = roles_by_slug.get("admin")
    sub_admin = roles_by_slug.get("sub-admin")
    supplier = roles_by_slug.get("supplier")
    agent_reseller = roles_by_slug.get("agent-reseller")
    customer = roles_by_slug.get("customer")

    # Super admin gets every permission
    if super_admin:
        for permission in permissions:
            assign_if_missing(db, super_admin, permission)
        seed_super_admin_user(db, super_admin)

    # Pre-compute slug lists used across multiple roles
    _customer_granular = [p["slug"] for p in CUSTOMER_GRANULAR_PERMISSIONS]
    _email_template_granular = [p["slug"] for p in EMAIL_TEMPLATE_GRANULAR_PERMISSIONS]
    _all_operational = [
        f"{module}.{action}"
        for module, _label, actions in OPERATIONAL_PERMISSIONS
        for action in actions
    ]
    _all_week = [
        f"{module}.{action}"
        for module, _label, actions in WEEK_11_15_PERMISSIONS
        for action in actions
    ]
    _week_no_system = [
        s for s in _all_week
        if not s.endswith(".manage_settings") and not s.endswith(".force_logout")
    ]

    default_role_permissions = {
        # ------------------------------------------------------------------
        # Admin -- full operational control; manages users, roles, permissions
        # ------------------------------------------------------------------
        admin: [
            # Dashboard
            "view-dashboard", "dashboard.view", "dashboard.summary",
            "dashboard.charts", "dashboard.activities", "dashboard.alerts",
            # Users
            "view-users", "create-users", "update-users", "delete-users",
            # Roles & Permissions
            "view-roles", "create-roles", "update-roles", "delete-roles",
            "view-permissions", "create-permissions", "update-permissions", "delete-permissions",
            # Customers (base + granular)
            "view-customers", "create-customers", "update-customers", "delete-customers",
            *_customer_granular,
            # Suppliers / Agents / Affiliates / Resellers (base)
            "view-suppliers", "create-suppliers", "update-suppliers", "delete-suppliers",
            "view-agents", "create-agents", "update-agents", "delete-agents",
            "view-affiliates", "create-affiliates", "update-affiliates", "delete-affiliates",
            "view-resellers", "create-resellers", "update-resellers",
            # Geo / CMS (base)
            "view-countries", "create-countries", "update-countries", "delete-countries",
            "view-cities", "create-cities", "update-cities", "delete-cities",
            "view-categories", "create-categories", "update-categories", "delete-categories",
            "view-subcategories", "create-subcategories", "update-subcategories", "delete-subcategories",
            # Tours (base)
            "view-tours", "create-tours", "update-tours", "delete-tours",
            # Bookings / Cancellations (base)
            "view-bookings", "create-bookings", "update-bookings", "delete-bookings",
            "view-cancellations", "update-cancellations",
            # Payments (base)
            "view-payments", "create-payments", "update-payments",
            "payments.summary",
            # Supplier Ledger (base + granular)
            "view-supplier_ledger", "create-supplier_ledger", "update-supplier_ledger",
            "supplier_ledger.view", "supplier_ledger.create_payout", "supplier_ledger.approve", "supplier_ledger.mark_paid",
            # Reports / Invoices (base)
            "view-reports", "view-invoices",
            # Notifications (base)
            "view-notifications", "create-notifications", "update-notifications",
            # Activity Logs / Sessions (base)
            "view-activity_logs", "view-sessions",
            # Email / Settings / Website CMS (base)
            "view-email", "create-email", "update-email", "delete-email", *_email_template_granular,
            "view-settings", "update-settings", "settings.view",
            "view-website_cms", "create-website_cms", "update-website_cms", "delete-website_cms",
            # Profile
            "view-profile", "update-profile", "profile.view",
            # All operational granular permissions
            *_all_operational,
            # All booking-lifecycle / financial / system granular permissions
            *_all_week,
        ],

        # ------------------------------------------------------------------
        # Sub Admin -- operations without system-level role/permission CRUD
        # ------------------------------------------------------------------
        sub_admin: [
            # Dashboard
            "view-dashboard", "dashboard.view", "dashboard.summary",
            "dashboard.charts", "dashboard.activities", "dashboard.alerts",
            # Users (no delete)
            "view-users", "create-users", "update-users",
            # Customers (base + granular, no delete)
            "view-customers", "create-customers", "update-customers",
            *[s for s in _customer_granular if s != "customers.export"],
            # Suppliers / Agents / Affiliates / Resellers (base, no delete)
            "view-suppliers", "create-suppliers", "update-suppliers",
            "view-agents", "create-agents", "update-agents",
            "view-affiliates", "create-affiliates", "update-affiliates",
            "view-resellers", "create-resellers", "update-resellers",
            # Geo / CMS (base, no delete)
            "view-countries", "create-countries", "update-countries",
            "view-cities", "create-cities", "update-cities",
            "view-categories", "create-categories", "update-categories",
            "view-subcategories", "create-subcategories", "update-subcategories",
            # Tours (base, no delete)
            "view-tours", "create-tours", "update-tours",
            # Bookings / Cancellations (base, no delete)
            "view-bookings", "create-bookings", "update-bookings",
            "view-cancellations", "update-cancellations",
            # Payments (view only, base)
            "view-payments", "payments.summary",
            # Supplier Ledger (view only)
            "view-supplier_ledger", "supplier_ledger.view",
            # Reports / Invoices (base)
            "view-reports", "view-invoices",
            # Notifications (base)
            "view-notifications", "create-notifications", "update-notifications",
            # Activity Logs (view only)
            "view-activity_logs",
            # Sessions (view only)
            "view-sessions",
            # Email (no delete)
            "view-email", "create-email", "update-email", "email_templates.view", "email_templates.create", "email_templates.edit",
            # Settings (view only)
            "view-settings", "settings.view",
            # Website CMS (no delete)
            "view-website_cms", "create-website_cms", "update-website_cms",
            # Profile
            "view-profile", "update-profile", "profile.view",
            # All operational granular permissions
            *_all_operational,
            # Week granular -- exclude system-only actions
            *_week_no_system,
        ],

        # ------------------------------------------------------------------
        # Supplier -- own data: tours, bookings on their tours, financials
        # ------------------------------------------------------------------
        supplier: [
            # Dashboard (limited)
            "view-dashboard", "dashboard.view", "dashboard.summary",
            # Supplier own profile
            "view-suppliers", "update-suppliers",
            "suppliers.view", "suppliers.edit", "suppliers.view_documents", "suppliers.request_commission",
            # Tours (create & manage own tours)
            "view-tours", "create-tours", "update-tours",
            "tours.view", "tours.create", "tours.edit", "tours.publish",
            # Bookings (view & status updates for their tours)
            "view-bookings",
            "bookings.view", "bookings.update_status", "bookings.view_history", "bookings.view_payments",
            # Cancellations (view only)
            "view-cancellations",
            "cancellations.view",
            # Payments (view only)
            "view-payments",
            "payments.view",
            # Reports (supplier-scoped)
            "view-reports",
            "reports.view", "reports.supplier",
            # Invoices (view + download)
            "view-invoices",
            "invoices.view", "invoices.download",
            # Notifications
            "view-notifications",
            "notifications.view",
            # Supplier Ledger (view own payouts)
            "view-supplier_ledger",
            "supplier_ledger.view", "supplier_ledger.create_payout",
            # Profile
            "view-profile", "update-profile", "profile.view",
        ],

        # ------------------------------------------------------------------
        # Agent / Reseller -- customer bookings and their own account
        # ------------------------------------------------------------------
        agent_reseller: [
            # Dashboard (limited)
            "view-dashboard", "dashboard.view", "dashboard.summary",
            # Agent own profile
            "view-agents", "update-agents",
            "agents.view", "agents.edit",
            # Resellers
            "view-resellers", "update-resellers",
            # Customer management
            "view-customers", "create-customers", "update-customers",
            "customers.view", "customers.create", "customers.edit",
            "customers.block", "customers.unblock", "customers.reset_password",
            "customers.view_bookings", "customers.view_payments",
            "customers.view_communications", "customers.communicate",
            # Tours (view only)
            "view-tours",
            "tours.view",
            # Bookings (create + manage)
            "view-bookings", "create-bookings", "update-bookings",
            "bookings.view", "bookings.create", "bookings.view_history", "bookings.view_payments",
            # Cancellations (view only)
            "view-cancellations",
            "cancellations.view",
            # Payments (view only)
            "view-payments",
            "payments.view",
            # Reports (agent-scoped)
            "view-reports",
            "reports.view", "reports.agent",
            # Invoices (view + download)
            "view-invoices",
            "invoices.view", "invoices.download",
            # Notifications
            "view-notifications",
            "notifications.view",
            # Profile
            "view-profile", "update-profile", "profile.view",
        ],

        # ------------------------------------------------------------------
        # Customer -- self-service: browse, book, pay, view own data
        # ------------------------------------------------------------------
        customer: [
            # Dashboard (minimal)
            "view-dashboard", "dashboard.view",
            # Tours (browse only)
            "view-tours",
            "tours.view",
            # Bookings (create + view own)
            "view-bookings", "create-bookings",
            "bookings.view", "bookings.create",
            # Cancellations (submit request, view own)
            "view-cancellations",
            "cancellations.view",
            # Payments (view own)
            "view-payments",
            "payments.view",
            # Invoices (view + download own)
            "view-invoices",
            "invoices.view", "invoices.download",
            # Notifications
            "view-notifications",
            "notifications.view",
            # Profile
            "view-profile", "update-profile", "profile.view",
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

