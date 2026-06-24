from sqlalchemy.orm import Session

from app.config import settings
from app.modules.admin_modules.models import AdminModule
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from app.modules.users.models import User, UserRole
from app.modules.cms.models import City, Country, Tour, TourCategory
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
    ("affiliates", "Affiliates"),
    ("resellers", "Resellers"),
    ("customers", "Customers"),
    ("countries", "Countries"),
    ("cities", "Cities"),
    ("tours", "Tours"),
    ("categories", "Tour Categories"),
    ("subcategories", "Tour Sub-Categories"),
    ("bookings", "Bookings"),
    ("payments", "Payments"),
    ("reports", "Reports"),
    ("invoices", "Invoices"),
    ("notifications", "Notifications"),
    ("activity_logs", "Activity Logs"),
    ("sessions", "Sessions"),
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

DASHBOARD_PERMISSIONS = [
    {"name": "View Dashboard", "slug": "dashboard.view", "module": "dashboard", "action": "get"},
    {"name": "View Dashboard Summary", "slug": "dashboard.summary", "module": "dashboard", "action": "get"},
    {"name": "View Dashboard Charts", "slug": "dashboard.charts", "module": "dashboard", "action": "get"},
    {"name": "View Dashboard Activities", "slug": "dashboard.activities", "module": "dashboard", "action": "get"},
    {"name": "View Dashboard Alerts", "slug": "dashboard.alerts", "module": "dashboard", "action": "get"},
    {"name": "View Payments", "slug": "payments.view", "module": "payments", "action": "get"},
    {"name": "View Payment Summary", "slug": "payments.summary", "module": "payments", "action": "get"},
    {"name": "View Reports", "slug": "reports.view", "module": "reports", "action": "get"},
    {"name": "Export Reports", "slug": "reports.export", "module": "reports", "action": "get"},
    {"name": "View Invoices", "slug": "invoices.view", "module": "invoices", "action": "get"},
    {"name": "View Activity Logs", "slug": "activity_logs.view", "module": "activity_logs", "action": "get"},
    {"name": "View Bookings", "slug": "bookings.view", "module": "bookings", "action": "get"},
    {"name": "View Settings", "slug": "settings.view", "module": "settings", "action": "get"},
    {"name": "View Profile", "slug": "profile.view", "module": "profile", "action": "get"},
]

DEFAULT_PERMISSIONS.extend(DASHBOARD_PERMISSIONS)

OPERATIONAL_PERMISSIONS = [
    ("suppliers", "Suppliers", ["view", "create", "edit", "approve", "reject", "partial_approve", "manage_markup", "view_documents", "reset_password", "communicate", "export"]),
    ("agents", "Agents", ["view", "create", "edit", "approve", "reject", "partial_approve", "manage_discount", "view_documents", "reset_password", "communicate", "export"]),
    ("affiliates", "Affiliates", ["view", "create", "approve", "reject", "manage_api_link", "view_documents", "export"]),
    ("countries", "Countries", ["view", "create", "edit", "disable"]),
    ("cities", "Cities", ["view", "create", "edit", "disable"]),
    ("categories", "Categories", ["view", "create", "edit", "disable"]),
    ("subcategories", "Sub-Categories", ["view", "create", "edit", "disable"]),
    ("tours", "Tours", ["view", "create", "edit", "publish", "disable"]),
]


WEEK_11_15_PERMISSIONS = [
    ("bookings", "Bookings", ["view", "create", "edit", "update_status", "assign_supplier", "cancel", "view_travellers", "view_payments", "view_history", "export"]),
    ("payments", "Payments", ["view", "create", "edit", "capture", "void", "refund", "view_transactions", "export", "manage_settings"]),
    ("invoices", "Invoices", ["view", "generate", "email", "download", "export"]),
    ("notifications", "Notifications", ["view", "manage", "retry"]),
    ("reports", "Reports", ["view", "admin", "supplier", "agent", "export"]),
    ("activity_logs", "Activity Logs", ["view", "export"]),
    ("sessions", "Sessions", ["view", "revoke", "force_logout"]),
]

for module, label, actions in WEEK_11_15_PERMISSIONS:
    for action in actions:
        DEFAULT_PERMISSIONS.append({"name": f"{action.replace('_', ' ').title()} {label}", "slug": f"{module}.{action}", "module": module, "action": action})
for module, label, actions in OPERATIONAL_PERMISSIONS:
    for action in actions:
        DEFAULT_PERMISSIONS.append(
            {
                "name": f"{action.replace('_', ' ').title()} {label}",
                "slug": f"{module}.{action}",
                "module": module,
                "action": action,
            }
        )


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



def seed_demo_tour_if_empty(db: Session):
    if db.query(Tour).first():
        return

    country = db.query(Country).filter(Country.country_code == "AE").first()
    if not country:
        country = Country(
            country_name="United Arab Emirates",
            country_code="AE",
            phone_code="+971",
            currency_code="AED",
            status="active",
        )
        db.add(country)
        db.flush()

    city = db.query(City).filter(City.country_id == country.id, City.city_name == "Dubai").first()
    if not city:
        city = City(country_id=country.id, city_name="Dubai", status="active")
        db.add(city)
        db.flush()

    category = db.query(TourCategory).filter(TourCategory.slug == "city-tours").first()
    if not category:
        category = TourCategory(
            category_name="City Tours",
            slug="city-tours",
            description="Curated city experiences",
            image="",
            status="active",
        )
        db.add(category)
        db.flush()

    tour = Tour(
        tour_code="TRV-DEMO-001",
        title="Dubai City Highlights",
        slug="dubai-city-highlights",
        subtitle="A compact guided Dubai experience",
        price_start_per_person=99.0,
        currency="AED",
        country_id=country.id,
        city_id=city.id,
        category_id=category.id,
        start_location="Dubai",
        finish_location="Dubai",
        number_of_days=1,
        short_description="A seeded tour used for local smoke checks and demos.",
        long_description="A seeded tour used for local smoke checks and demos.",
        seo_title="Dubai City Highlights",
        seo_description="A compact guided Dubai experience.",
        seo_keywords="dubai,city,tour",
        image_alt_text="Dubai skyline",
        status="published",
    )
    db.add(tour)
    db.commit()
def seed_default_roles_and_permissions(db: Session):
    for slug, name in MODULES:
        admin_module = db.query(AdminModule).filter(AdminModule.slug == slug).first()

        if not admin_module:
            db.add(
                AdminModule(
                    name=name,
                    slug=slug,
                    description=f"{name} admin module",
                    is_active=True,
                    is_system=True,
                )
            )
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
            "dashboard.view",
            "dashboard.summary",
            "dashboard.charts",
            "dashboard.activities",
            "dashboard.alerts",
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
            "customers.view",
            "customers.create",
            "customers.edit",
            "customers.block",
            "customers.unblock",
            "customers.reset_password",
            "customers.view_bookings",
            "customers.view_payments",
            "customers.view_communications",
            "customers.communicate",
            "customers.export",
            "view-tours",
            "create-tours",
            "update-tours",
            "view-bookings",
            "create-bookings",
            "update-bookings",
            "view-payments",
            "payments.view",
            "payments.summary",
            "view-reports",
            "reports.view",
            "reports.export",
            "invoices.view",
            "activity_logs.view",
            "bookings.view",
            "settings.view",
            "profile.view",
            "view-email",
            "create-email",
            "update-email",
            "view-settings",
            "update-settings",
            "view-profile",
            "update-profile",
            *[f"{module}.{action}" for module, _label, actions in OPERATIONAL_PERMISSIONS for action in actions],
        ],
        sub_admin: [
            "view-dashboard",
            "dashboard.view",
            "dashboard.summary",
            "dashboard.charts",
            "dashboard.activities",
            "dashboard.alerts",
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
            "customers.view",
            "customers.create",
            "customers.edit",
            "customers.block",
            "customers.unblock",
            "customers.reset_password",
            "customers.view_bookings",
            "customers.view_payments",
            "customers.view_communications",
            "customers.communicate",
            "view-tours",
            "create-tours",
            "update-tours",
            "view-bookings",
            "create-bookings",
            "update-bookings",
            "view-payments",
            "payments.view",
            "view-reports",
            "reports.view",
            "bookings.view",
            "profile.view",
            "view-email",
            "create-email",
            "update-email",
            "view-settings",
            "view-profile",
            "update-profile",
            "suppliers.view",
            "suppliers.create",
            "suppliers.edit",
            "suppliers.approve",
            "suppliers.reject",
            "suppliers.partial_approve",
            "suppliers.manage_markup",
            "suppliers.view_documents",
            "agents.view",
            "agents.create",
            "agents.edit",
            "agents.approve",
            "agents.reject",
            "agents.partial_approve",
            "agents.manage_discount",
            "agents.view_documents",
            "affiliates.view",
            "affiliates.approve",
            "affiliates.reject",
            "affiliates.manage_api_link",
            "countries.view",
            "countries.create",
            "countries.edit",
            "countries.disable",
            "cities.view",
            "cities.create",
            "cities.edit",
            "cities.disable",
            "categories.view",
            "categories.create",
            "categories.edit",
            "categories.disable",
            "subcategories.view",
            "subcategories.create",
            "subcategories.edit",
            "subcategories.disable",
            "tours.view",
            "tours.create",
            "tours.edit",
            "tours.publish",
            "tours.disable",
        ],
        supplier: [
            "view-dashboard",
            "dashboard.view",
            "dashboard.summary",
            "dashboard.charts",
            "dashboard.activities",
            "dashboard.alerts",
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
            "profile.view",
            "update-profile",
            "suppliers.view",
            "suppliers.edit",
            "suppliers.view_documents",
            "tours.view",
            "tours.create",
            "tours.edit",
        ],
        agent_reseller: [
            "view-dashboard",
            "dashboard.view",
            "dashboard.summary",
            "dashboard.charts",
            "dashboard.activities",
            "dashboard.alerts",
            "view-agents",
            "update-agents",
            "view-resellers",
            "update-resellers",
            "view-customers",
            "create-customers",
            "update-customers",
            "customers.view",
            "customers.create",
            "customers.edit",
            "customers.block",
            "customers.unblock",
            "customers.reset_password",
            "customers.view_bookings",
            "customers.view_payments",
            "customers.view_communications",
            "customers.communicate",
            "view-tours",
            "view-bookings",
            "create-bookings",
            "update-bookings",
            "view-payments",
            "payments.view",
            "view-reports",
            "reports.view",
            "view-profile",
            "profile.view",
            "update-profile",
            "agents.view",
            "agents.edit",
            "tours.view",
        ],
        customer: [
            "view-dashboard",
            "dashboard.view",
            "dashboard.summary",
            "dashboard.charts",
            "dashboard.activities",
            "dashboard.alerts",
            "view-tours",
            "view-bookings",
            "bookings.view",
            "create-bookings",
            "view-payments",
            "payments.view",
            "view-profile",
            "profile.view",
            "update-profile",
        ],
    }

    week_permission_slugs = [f"{module}.{action}" for module, _label, actions in WEEK_11_15_PERMISSIONS for action in actions]
    if admin:
        default_role_permissions.setdefault(admin, []).extend(week_permission_slugs)
    if sub_admin:
        default_role_permissions.setdefault(sub_admin, []).extend([
            slug for slug in week_permission_slugs
            if not slug.endswith(".manage_settings") and not slug.endswith(".force_logout")
        ])
    if supplier:
        default_role_permissions.setdefault(supplier, []).extend(["bookings.view", "bookings.update_status", "bookings.view_history", "payments.view", "reports.supplier", "notifications.view"])
    if agent_reseller:
        default_role_permissions.setdefault(agent_reseller, []).extend(["bookings.view", "bookings.create", "bookings.view_history", "payments.view", "reports.agent", "notifications.view"])
    if customer:
        default_role_permissions.setdefault(customer, []).extend(["bookings.view", "bookings.create", "payments.view", "invoices.view", "invoices.download", "notifications.view"])
    for role, permission_slugs in default_role_permissions.items():
        if not role:
            continue

        for slug in permission_slugs:
            permission = permissions_by_slug.get(slug)

            if permission:
                assign_if_missing(db, role, permission)

    db.commit()
    seed_demo_tour_if_empty(db)


