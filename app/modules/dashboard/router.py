import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.audit.models import AuditLog
from app.modules.common.auth import get_current_user, require_any_permission
from app.modules.users.models import User
from app.modules.roles.models import Role
from app.modules.permissions.models import Permission, RolePermission
from app.modules.users.models import UserRole
from app.modules.common.media import existing_storage_path
from app.modules.suppliers.models import Supplier
from app.modules.agents.models import Agent
from app.modules.affiliates.models import Affiliate
from app.modules.cms.models import Tour
from app.modules.bookings.models import Booking
from app.modules.payments.models import Payment
from app.modules.customers.models import Customer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Maps role slug → dashboard type key used by the frontend
ROLE_TO_DASHBOARD_TYPE = {
    "super-admin": "super_admin",
    "admin": "admin",
    "sub-admin": "sub_admin",
    "supplier": "supplier",
    "agent-reseller": "agent",
    "customer": "customer",
    "affiliate": "affiliate",
}

# Role-specific sidebar menus for non-admin roles
ROLE_SIDEBAR = {
    "supplier": [
        {"label": "Dashboard", "module": "dashboard", "permission": "view-dashboard"},
        {"label": "My Bookings", "module": "bookings", "permission": "view-bookings"},
        {"label": "Upcoming Bookings", "module": "bookings", "permission": "view-bookings"},
        {"label": "Accepted Bookings", "module": "bookings", "permission": "view-bookings"},
        {"label": "Declined Bookings", "module": "bookings", "permission": "view-bookings"},
        {"label": "Payments", "module": "payments", "permission": "view-payments"},
        {"label": "Profile", "module": "profile", "permission": "view-profile"},
        {"label": "Documents", "module": "suppliers", "permission": "suppliers.view_documents"},
        {"label": "Notifications", "module": "dashboard", "permission": "view-dashboard"},
    ],
    "agent-reseller": [
        {"label": "Dashboard", "module": "dashboard", "permission": "view-dashboard"},
        {"label": "Create Booking", "module": "bookings", "permission": "create-bookings"},
        {"label": "My Bookings", "module": "bookings", "permission": "view-bookings"},
        {"label": "Customers", "module": "customers", "permission": "view-customers"},
        {"label": "Payments", "module": "payments", "permission": "view-payments"},
        {"label": "Invoices", "module": "payments", "permission": "view-payments"},
        {"label": "Discount / Commission", "module": "agents", "permission": "agents.view"},
        {"label": "Profile", "module": "profile", "permission": "view-profile"},
        {"label": "Notifications", "module": "dashboard", "permission": "view-dashboard"},
    ],
    "customer": [
        {"label": "Dashboard", "module": "dashboard", "permission": "view-dashboard"},
        {"label": "My Bookings", "module": "bookings", "permission": "view-bookings"},
        {"label": "Upcoming Tours", "module": "bookings", "permission": "view-bookings"},
        {"label": "Completed Tours", "module": "bookings", "permission": "view-bookings"},
        {"label": "Payments", "module": "payments", "permission": "view-payments"},
        {"label": "Invoices", "module": "payments", "permission": "view-payments"},
        {"label": "Profile", "module": "profile", "permission": "view-profile"},
        {"label": "Notifications", "module": "dashboard", "permission": "view-dashboard"},
    ],
    "affiliate": [
        {"label": "Dashboard", "module": "dashboard", "permission": "view-dashboard"},
        {"label": "Affiliate Profile", "module": "affiliates", "permission": "affiliates.view"},
        {"label": "API Link", "module": "affiliates", "permission": "affiliates.view"},
        {"label": "Referrals", "module": "affiliates", "permission": "affiliates.view"},
        {"label": "Invoicing", "module": "affiliates", "permission": "affiliates.view"},
        {"label": "Notifications", "module": "dashboard", "permission": "view-dashboard"},
    ],
}

# Permission slug → sidebar menu mapping for admin/sub-admin roles
PERMISSION_MENU_MAP = {
    "view-dashboard": {"label": "Dashboard", "module": "dashboard"},
    "dashboard.view": {"label": "Dashboard", "module": "dashboard"},
    "view-users": {"label": "Users", "module": "users"},
    "view-roles": {"label": "Roles", "module": "roles"},
    "view-permissions": {"label": "Permissions", "module": "permissions"},
    "suppliers.view": {"label": "Suppliers", "module": "suppliers"},
    "view-suppliers": {"label": "Suppliers", "module": "suppliers"},
    "agents.view": {"label": "Agents", "module": "agents"},
    "view-agents": {"label": "Agents", "module": "agents"},
    "affiliates.view": {"label": "Affiliates", "module": "affiliates"},
    "view-affiliates": {"label": "Affiliates", "module": "affiliates"},
    "customers.view": {"label": "Customers", "module": "customers"},
    "view-customers": {"label": "Customers", "module": "customers"},
    "countries.view": {"label": "Countries", "module": "countries"},
    "view-countries": {"label": "Countries", "module": "countries"},
    "cities.view": {"label": "Cities", "module": "cities"},
    "view-cities": {"label": "Cities", "module": "cities"},
    "tours.view": {"label": "Tours", "module": "tours"},
    "view-tours": {"label": "Tours", "module": "tours"},
    "categories.view": {"label": "Tour Categories", "module": "categories"},
    "subcategories.view": {"label": "Tour Subcategories", "module": "subcategories"},
    "view-bookings": {"label": "Bookings", "module": "bookings"},
    "bookings.view": {"label": "Bookings", "module": "bookings"},
    "view-payments": {"label": "Payments", "module": "payments"},
    "payments.view": {"label": "Payments", "module": "payments"},
    "view-reports": {"label": "Reports", "module": "reports"},
    "reports.view": {"label": "Reports", "module": "reports"},
    "invoices.view": {"label": "Invoices", "module": "invoices"},
    "view-email": {"label": "Email Templates", "module": "email"},
    "view-settings": {"label": "Settings", "module": "settings"},
    "activity_logs.view": {"label": "Activity Logs", "module": "activity_logs"},
    "view-profile": {"label": "Profile", "module": "profile"},
    "profile.view": {"label": "Profile", "module": "profile"},
}

# Ordered list of menu modules to control display order
ADMIN_MENU_ORDER = [
    "dashboard", "users", "roles", "permissions", "customers", "suppliers",
    "agents", "affiliates", "countries", "cities", "tours", "categories",
    "subcategories", "bookings", "payments", "invoices", "reports", "email",
    "settings", "activity_logs", "profile",
]


def _filters_payload(
    start_date: date | None,
    end_date: date | None,
    country_id: int | None,
):
    return {
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "country_id": country_id,
    }


def _role_ids_for_user(user: User):
    role_ids = {user.role_id} if user.role_id else set()
    role_ids.update(ur.role_id for ur in user.user_roles)
    return [rid for rid in role_ids if rid]


def _get_user_permissions(user: User, db: Session) -> list[Permission]:
    role_ids = _role_ids_for_user(user)
    if not role_ids:
        return []
    return (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id.in_(role_ids))
        .filter(Permission.is_active == True)
        .distinct()
        .all()
    )


def _build_admin_menus(permissions: list[Permission]) -> list[dict]:
    seen_modules: set[str] = set()
    module_to_menu: dict[str, dict] = {}

    for perm in permissions:
        entry = PERMISSION_MENU_MAP.get(perm.slug)
        if entry and entry["module"] not in seen_modules:
            seen_modules.add(entry["module"])
            module_to_menu[entry["module"]] = {
                "label": entry["label"],
                "module": entry["module"],
                "permission": perm.slug,
            }

    ordered = []
    for module in ADMIN_MENU_ORDER:
        if module in module_to_menu:
            ordered.append(module_to_menu[module])

    return ordered


def _get_role_slug(user: User) -> str:
    return user.role.slug if user.role else ""


def _get_dashboard_type(role_slug: str) -> str:
    return ROLE_TO_DASHBOARD_TYPE.get(role_slug, "admin")


def _safe_count(db, model_class, *filters):
    try:
        q = db.query(model_class)
        for f in filters:
            q = q.filter(f)
        return q.count()
    except Exception:
        return 0


def _safe_sum(db, column, *filters):
    try:
        q = db.query(sqlfunc.coalesce(sqlfunc.sum(column), 0))
        for f in filters:
            q = q.filter(f)
        return float(q.scalar() or 0)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# GET /dashboard/me
# ---------------------------------------------------------------------------

@router.get("/me")
def my_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role_slug = _get_role_slug(current_user)
    dashboard_type = _get_dashboard_type(role_slug)
    permissions = _get_user_permissions(current_user, db)
    permission_slugs = {p.slug for p in permissions}

    # Build sidebar based on role
    if role_slug in ROLE_SIDEBAR:
        menus = ROLE_SIDEBAR[role_slug]
        sidebar_menu = menus
    else:
        menus = _build_admin_menus(permissions)
        sidebar_menu = menus

    # Allowed modules from permissions
    allowed_modules = list({p.module for p in permissions})

    # Permission helpers
    can_view_users = "view-users" in permission_slugs or "users.view" in permission_slugs
    can_manage_users = can_view_users or "update-users" in permission_slugs
    can_view_roles = "view-roles" in permission_slugs or "roles.view" in permission_slugs

    total_users = db.query(User).count() if can_view_users else 0
    active_users = db.query(User).filter(User.is_active == True).count() if can_view_users else 0
    pending_users = db.query(User).filter(User.approval_status == "pending").count() if can_manage_users else 0
    total_roles = db.query(Role).filter(Role.is_active == True).count() if can_view_roles else 0

    pending_approval_users = []
    if can_manage_users:
        pending_approval_users = (
            db.query(User)
            .filter(User.approval_status == "pending")
            .order_by(User.id.desc())
            .limit(5)
            .all()
        )

    # Approval status for supplier/agent/affiliate
    profile_status = None
    approval_status = None
    supplier_id = None
    agent_id = None
    affiliate_id = None

    if role_slug == "supplier":
        supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
        if supplier:
            supplier_id = supplier.id
            profile_status = supplier.status
            approval_status = supplier.approval_status
    elif role_slug == "agent-reseller":
        agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
        if agent:
            agent_id = agent.id
            profile_status = agent.status
            approval_status = agent.approval_status
    elif role_slug == "affiliate":
        affiliate = db.query(Affiliate).filter(
            (Affiliate.user_id == current_user.id) | (Affiliate.email == current_user.email)
        ).first()
        if affiliate:
            affiliate_id = affiliate.id
            profile_status = affiliate.status
            approval_status = affiliate.approval_status

    return {
        "status": "success",
        "data": {
            "user": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
                "user_type": role_slug,
                "profile_image": existing_storage_path(current_user.profile_image),
                "role": {
                    "id": current_user.role.id if current_user.role else None,
                    "name": current_user.role.name if current_user.role else None,
                    "slug": current_user.role.slug if current_user.role else None,
                },
                "profile_status": profile_status,
                "approval_status": approval_status,
                "customer_id": (lambda c: c.id if c else None)(db.query(Customer).filter(Customer.user_id == current_user.id).first()) if role_slug == "customer" else None,
                "supplier_id": supplier_id,
                "agent_id": agent_id,
                "affiliate_id": affiliate_id,
            },
            "permissions": [
                {
                    "name": p.name,
                    "slug": p.slug,
                    "module": p.module,
                    "action": p.action,
                }
                for p in permissions
            ],
            "allowed_modules": allowed_modules,
            "menus": menus,
            "sidebar_menu": sidebar_menu,
            "dashboard_type": dashboard_type,
            "stats": {
                "users": total_users,
                "active_users": active_users,
                "roles": total_roles,
                "permissions": len(permissions),
                "pending_users": pending_users,
            },
            "pending_approvals": [
                {
                    "id": u.id,
                    "name": u.name,
                    "email": u.email,
                    "role_id": u.role_id,
                    "role_name": u.role.name if u.role else None,
                    "created_at": u.created_at,
                }
                for u in pending_approval_users
            ],
        },
    }


# ---------------------------------------------------------------------------
# GET /dashboard/summary
# ---------------------------------------------------------------------------

@router.get("/summary")
def dashboard_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    agent_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("dashboard.view", "view-dashboard")),
):
    role_slug = _get_role_slug(current_user)
    filters = _filters_payload(start_date, end_date, country_id)

    # Supplier-scoped summary
    if role_slug == "supplier":
        supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
        if not supplier:
            return {"status": "success", "data": {**filters, **_empty_supplier_summary()}}

        sid = supplier.id
        total_bookings = _safe_count(db, Booking, Booking.supplier_id == sid)
        upcoming = _safe_count(db, Booking, Booking.supplier_id == sid, Booking.booking_status == "upcoming")
        accepted = _safe_count(db, Booking, Booking.supplier_id == sid, Booking.booking_status == "ongoing")
        completed = _safe_count(db, Booking, Booking.supplier_id == sid, Booking.booking_status == "completed")
        cancelled = _safe_count(db, Booking, Booking.supplier_id == sid, Booking.booking_status == "cancelled")

        return {
            "status": "success",
            "data": {
                **filters,
                "dashboard_type": "supplier",
                "total_bookings": total_bookings,
                "upcoming_bookings": upcoming,
                "accepted_bookings": accepted,
                "declined_bookings": 0,
                "completed_bookings": completed,
                "cancelled_bookings": cancelled,
                "pending_payments": _safe_sum(db, Payment.pending_amount, Payment.payment_status.in_(["pending", "partial"])),
                "profile_approval_status": supplier.approval_status,
                "document_verification_status": "pending",
            },
        }

    # Agent-scoped summary
    if role_slug == "agent-reseller":
        agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
        if not agent:
            return {"status": "success", "data": {**filters, **_empty_agent_summary()}}

        aid = agent.id
        total_bookings = _safe_count(db, Booking, Booking.agent_id == aid)
        upcoming = _safe_count(db, Booking, Booking.agent_id == aid, Booking.booking_status == "upcoming")
        completed = _safe_count(db, Booking, Booking.agent_id == aid, Booking.booking_status == "completed")
        cancelled = _safe_count(db, Booking, Booking.agent_id == aid, Booking.booking_status == "cancelled")

        return {
            "status": "success",
            "data": {
                **filters,
                "dashboard_type": "agent",
                "total_bookings": total_bookings,
                "upcoming_bookings": upcoming,
                "completed_bookings": completed,
                "cancelled_bookings": cancelled,
                "pending_payments": 0.0,
                "discount_type": agent.discount_type,
                "discount_value": float(agent.discount_value or 0),
                "agent_approval_status": agent.approval_status,
            },
        }

    # Customer-scoped summary
    if role_slug == "customer":
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        if not customer:
            return {"status": "success", "data": {**filters, **_empty_customer_summary()}}

        cid = customer.id
        active_customer_statuses = ["pending_payment", "payment_authorized", "pending_supplier_acceptance", "confirmed", "upcoming", "ongoing"]
        total_bookings = _safe_count(db, Booking, Booking.customer_id == cid)
        upcoming = _safe_count(db, Booking, Booking.customer_id == cid, Booking.booking_status.in_(active_customer_statuses))
        completed = _safe_count(db, Booking, Booking.customer_id == cid, Booking.booking_status == "completed")
        cancelled = _safe_count(db, Booking, Booking.customer_id == cid, Booking.booking_status == "cancelled")
        paid_amount = _safe_sum(db, Booking.amount_paid, Booking.customer_id == cid)
        pending_amount = _safe_sum(db, Booking.amount_pending, Booking.customer_id == cid)
        return {
            "status": "success",
            "data": {
                **filters,
                "dashboard_type": "customer",
                "total_bookings": total_bookings,
                "upcoming_tours": upcoming,
                "completed_tours": completed,
                "cancelled_tours": cancelled,
                "pending_payments": pending_amount,
                "paid_amount": paid_amount,
                "profile_status": customer.status,
            },
        }

    # Affiliate summary
    if role_slug == "affiliate":
        affiliate = db.query(Affiliate).filter(
            (Affiliate.user_id == current_user.id) | (Affiliate.email == current_user.email)
        ).first()
        marketing = None
        if affiliate and affiliate.marketing_info:
            marketing = affiliate.marketing_info

        return {
            "status": "success",
            "data": {
                **filters,
                "dashboard_type": "affiliate",
                "approval_status": affiliate.approval_status if affiliate else "pending",
                "api_link_status": "active" if (affiliate and affiliate.api_link) else "inactive",
                "estimated_monthly_bookings": marketing.estimated_monthly_bookings if marketing else 0,
            },
        }

    # Admin / Sub-Admin / Super-Admin — permission-scoped
    role_ids = _role_ids_for_user(current_user)
    slugs: set[str] = set()
    if role_ids:
        slugs = {
            p.slug
            for p in db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id.in_(role_ids))
            .filter(Permission.is_active == True)
            .all()
        }

    def _can(*checks: str) -> bool:
        return any(s in slugs for s in checks)

    can_suppliers = _can("suppliers.view", "view-suppliers")
    can_agents = _can("agents.view", "view-agents")
    can_affiliates = _can("affiliates.view", "view-affiliates")
    can_tours = _can("tours.view", "view-tours")
    can_payments = _can("payments.view", "view-payments")

    total_suppliers = _safe_count(db, Supplier) if can_suppliers else 0
    pending_suppliers = _safe_count(db, Supplier, Supplier.approval_status == "pending") if can_suppliers else 0
    approved_suppliers = total_suppliers - pending_suppliers

    total_agents = _safe_count(db, Agent) if can_agents else 0
    pending_agents = _safe_count(db, Agent, Agent.approval_status == "pending") if can_agents else 0
    approved_agents = total_agents - pending_agents

    total_affiliates = _safe_count(db, Affiliate) if can_affiliates else 0
    pending_affiliates = _safe_count(db, Affiliate, Affiliate.approval_status == "pending") if can_affiliates else 0

    total_tours = _safe_count(db, Tour) if can_tours else 0
    published_tours = _safe_count(db, Tour, Tour.status == "published") if can_tours else 0

    total_bookings = _safe_count(db, Booking)
    upcoming_bookings = _safe_count(db, Booking, Booking.booking_status == "upcoming")
    total_customers = db.query(User).count()
    pending_admin_users = db.query(User).filter(User.approval_status == "pending").count()

    total_revenue = _safe_sum(db, Payment.paid_amount, Payment.payment_status != "refunded") if can_payments else 0.0
    pending_payments = _safe_sum(db, Payment.pending_amount, Payment.payment_status.in_(["pending", "partial"])) if can_payments else 0.0

    return {
        "status": "success",
        "data": {
            **filters,
            "dashboard_type": _get_dashboard_type(role_slug),
            "total_bookings": total_bookings,
            "total_customers": total_customers,
            "total_suppliers": total_suppliers,
            "approved_suppliers": approved_suppliers,
            "pending_suppliers": pending_suppliers,
            "total_agents": total_agents,
            "approved_agents": approved_agents,
            "pending_agents": pending_agents,
            "total_affiliates": total_affiliates,
            "pending_affiliates": pending_affiliates,
            "total_tours": total_tours,
            "published_tours": published_tours,
            "active_admin_users": db.query(User).filter(User.is_active == True).count(),
            "pending_admin_users": pending_admin_users,
            "total_revenue": total_revenue,
            "pending_payments": pending_payments,
            "upcoming_bookings": upcoming_bookings,
        },
    }


def _empty_supplier_summary():
    return {
        "dashboard_type": "supplier",
        "total_bookings": 0,
        "upcoming_bookings": 0,
        "accepted_bookings": 0,
        "declined_bookings": 0,
        "completed_bookings": 0,
        "cancelled_bookings": 0,
        "pending_payments": 0.0,
        "profile_approval_status": "pending",
        "document_verification_status": "pending",
    }


def _empty_agent_summary():
    return {
        "dashboard_type": "agent",
        "total_bookings": 0,
        "upcoming_bookings": 0,
        "completed_bookings": 0,
        "cancelled_bookings": 0,
        "pending_payments": 0.0,
        "discount_type": None,
        "discount_value": 0.0,
        "agent_approval_status": "pending",
    }


def _empty_customer_summary():
    return {
        "dashboard_type": "customer",
        "total_bookings": 0,
        "upcoming_tours": 0,
        "completed_tours": 0,
        "cancelled_tours": 0,
        "pending_payments": 0.0,
        "paid_amount": 0.0,
        "profile_status": "active",
    }


# ---------------------------------------------------------------------------
# GET /dashboard/charts
# ---------------------------------------------------------------------------

@router.get("/charts")
def dashboard_charts(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("dashboard.view", "view-dashboard")),
):
    role_slug = _get_role_slug(current_user)
    filters = _filters_payload(start_date, end_date, country_id)

    # Supplier charts
    if role_slug == "supplier":
        supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
        sid = supplier.id if supplier else -1

        booking_statuses = _booking_status_chart(db, Booking.supplier_id == sid)
        return {
            "status": "success",
            "data": {
                **filters,
                "dashboard_type": "supplier",
                "booking_status_chart": booking_statuses,
                "monthly_bookings": [],
                "payment_status_chart": [],
            },
        }

    # Agent charts
    if role_slug == "agent-reseller":
        agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
        aid = agent.id if agent else -1

        booking_statuses = _booking_status_chart(db, Booking.agent_id == aid)
        return {
            "status": "success",
            "data": {
                **filters,
                "dashboard_type": "agent",
                "booking_status_chart": booking_statuses,
                "monthly_bookings": [],
                "payment_status_chart": [],
            },
        }

    # Customer charts
    if role_slug == "customer":
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        cid = customer.id if customer else -1

        booking_statuses = _booking_status_chart(db, Booking.customer_id == cid)
        return {
            "status": "success",
            "data": {
                **filters,
                "dashboard_type": "customer",
                "booking_status_chart": booking_statuses,
                "payment_status_chart": [],
            },
        }

    # Affiliate charts
    if role_slug == "affiliate":
        return {
            "status": "success",
            "data": {
                **filters,
                "dashboard_type": "affiliate",
                "booking_status_chart": [],
                "referral_trend": [],
            },
        }

    # Admin/Super Admin charts
    booking_statuses = _booking_status_chart(db)
    payment_statuses = _payment_status_chart(db)

    return {
        "status": "success",
        "data": {
            **filters,
            "dashboard_type": _get_dashboard_type(role_slug),
            "booking_status_chart": booking_statuses,
            "payment_status_chart": payment_statuses,
            "supplier_status_chart": _supplier_status_chart(db),
            "agent_status_chart": _agent_status_chart(db),
            "monthly_booking_trend": [],
            "top_destinations": [],
        },
    }


def _booking_status_chart(db: Session, *filters):
    statuses = ["upcoming", "ongoing", "completed", "cancelled"]
    result = []
    for status in statuses:
        try:
            q = db.query(Booking).filter(Booking.booking_status == status)
            for f in filters:
                q = q.filter(f)
            result.append({"status": status, "count": q.count()})
        except Exception:
            result.append({"status": status, "count": 0})
    return result


def _payment_status_chart(db: Session):
    statuses = ["paid", "partial", "pending", "failed", "refunded"]
    result = []
    for status in statuses:
        try:
            result.append({"status": status, "count": db.query(Payment).filter(Payment.payment_status == status).count()})
        except Exception:
            result.append({"status": status, "count": 0})
    return result


def _supplier_status_chart(db: Session):
    statuses = ["approved", "pending", "rejected"]
    result = []
    for status in statuses:
        try:
            result.append({"status": status, "count": db.query(Supplier).filter(Supplier.approval_status == status).count()})
        except Exception:
            result.append({"status": status, "count": 0})
    return result


def _agent_status_chart(db: Session):
    statuses = ["approved", "pending", "rejected"]
    result = []
    for status in statuses:
        try:
            result.append({"status": status, "count": db.query(Agent).filter(Agent.approval_status == status).count()})
        except Exception:
            result.append({"status": status, "count": 0})
    return result


# ---------------------------------------------------------------------------
# GET /dashboard/recent-activities
# ---------------------------------------------------------------------------

@router.get("/recent-activities")
def recent_activities(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("dashboard.view", "view-dashboard")),
):
    role_slug = _get_role_slug(current_user)

    # Supplier — their booking activities
    if role_slug == "supplier":
        supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
        sid = supplier.id if supplier else -1

        bookings = (
            db.query(Booking)
            .filter(Booking.supplier_id == sid)
            .order_by(Booking.created_at.desc())
            .limit(10)
            .all()
        )
        return {
            "status": "success",
            "data": {
                "dashboard_type": "supplier",
                "recent_bookings": [
                    {
                        "id": b.id,
                        "booking_code": b.booking_code,
                        "tour_name": b.tour_name,
                        "booking_status": b.booking_status,
                        "created_at": b.created_at,
                    }
                    for b in bookings
                ],
            },
        }

    # Agent — their booking activities
    if role_slug == "agent-reseller":
        agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
        aid = agent.id if agent else -1

        bookings = (
            db.query(Booking)
            .filter(Booking.agent_id == aid)
            .order_by(Booking.created_at.desc())
            .limit(10)
            .all()
        )
        return {
            "status": "success",
            "data": {
                "dashboard_type": "agent",
                "recent_bookings": [
                    {
                        "id": b.id,
                        "booking_code": b.booking_code,
                        "tour_name": b.tour_name,
                        "booking_status": b.booking_status,
                        "created_at": b.created_at,
                    }
                    for b in bookings
                ],
            },
        }

    # Customer — their own bookings
    if role_slug == "customer":
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        cid = customer.id if customer else -1

        bookings = (
            db.query(Booking)
            .filter(Booking.customer_id == cid)
            .order_by(Booking.created_at.desc())
            .limit(10)
            .all()
        )
        return {
            "status": "success",
            "data": {
                "dashboard_type": "customer",
                "recent_bookings": [
                    {
                        "id": b.id,
                        "booking_code": b.booking_code,
                        "tour_name": b.tour_name,
                        "booking_status": b.booking_status,
                        "created_at": b.created_at,
                    }
                    for b in bookings
                ],
            },
        }

    # Affiliate
    if role_slug == "affiliate":
        return {
            "status": "success",
            "data": {
                "dashboard_type": "affiliate",
                "recent_activities": [],
            },
        }

    # Admin / Sub-Admin / Super-Admin — audit log
    admin_actions = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(10)
        .all()
    )

    return {
        "status": "success",
        "data": {
            "dashboard_type": _get_dashboard_type(role_slug),
            "recent_bookings": [],
            "recent_suppliers": [],
            "recent_agents": [],
            "recent_payments": [],
            "recent_admin_actions": [
                {
                    "id": item.id,
                    "actor_user_id": item.actor_user_id,
                    "action": item.action,
                    "entity_type": item.entity_type,
                    "entity_id": item.entity_id,
                    "created_at": item.created_at,
                }
                for item in admin_actions
            ],
        },
    }


# ---------------------------------------------------------------------------
# GET /dashboard/alerts
# ---------------------------------------------------------------------------

@router.get("/alerts")
def dashboard_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("dashboard.view", "view-dashboard")),
):
    role_slug = _get_role_slug(current_user)

    # Supplier alerts
    if role_slug == "supplier":
        supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
        alerts = []

        if supplier:
            new_bookings = _safe_count(db, Booking, Booking.supplier_id == supplier.id, Booking.booking_status == "upcoming")
            if new_bookings > 0:
                alerts.append({"type": "info", "message": f"{new_bookings} new booking(s) assigned to you", "action": "my-bookings"})

            if supplier.approval_status == "pending":
                alerts.append({"type": "warning", "message": "Your supplier profile is pending approval", "action": "profile"})
            elif supplier.approval_status == "rejected":
                alerts.append({"type": "error", "message": "Your supplier profile was rejected. Please update your documents.", "action": "documents"})

        return {"status": "success", "data": {"dashboard_type": "supplier", "alerts": alerts}}

    # Agent alerts
    if role_slug == "agent-reseller":
        agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
        alerts = []

        if agent:
            pending_bookings = _safe_count(db, Booking, Booking.agent_id == agent.id, Booking.payment_status == "pending")
            if pending_bookings > 0:
                alerts.append({"type": "warning", "message": f"{pending_bookings} booking(s) have pending payments", "action": "payments"})

            if agent.approval_status == "pending":
                alerts.append({"type": "warning", "message": "Your agent profile is pending approval", "action": "profile"})
            elif agent.approval_status == "rejected":
                alerts.append({"type": "error", "message": "Your agent profile was rejected. Please contact support.", "action": "profile"})

        return {"status": "success", "data": {"dashboard_type": "agent", "alerts": alerts}}

    # Customer alerts
    if role_slug == "customer":
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        alerts = []

        if customer:
            active_customer_statuses = ["pending_payment", "payment_authorized", "pending_supplier_acceptance", "confirmed", "upcoming", "ongoing"]
            pending_amount = _safe_sum(db, Booking.amount_pending, Booking.customer_id == customer.id)
            if pending_amount > 0:
                alerts.append({"type": "warning", "message": f"You have AED {pending_amount:,.0f} in pending payments", "action": "payments"})

            upcoming = _safe_count(db, Booking, Booking.customer_id == customer.id, Booking.booking_status.in_(active_customer_statuses))
            if upcoming > 0:
                alerts.append({"type": "info", "message": f"You have {upcoming} active booking(s)", "action": "bookings"})
        return {"status": "success", "data": {"dashboard_type": "customer", "alerts": alerts}}

    # Affiliate alerts
    if role_slug == "affiliate":
        affiliate = db.query(Affiliate).filter(
            (Affiliate.user_id == current_user.id) | (Affiliate.email == current_user.email)
        ).first()
        alerts = []

        if affiliate:
            if affiliate.approval_status == "pending":
                alerts.append({"type": "warning", "message": "Your affiliate application is pending review", "action": "profile"})
            elif affiliate.approval_status == "approved" and not affiliate.api_link:
                alerts.append({"type": "info", "message": "Your affiliate account is approved. Request your API link.", "action": "api-link"})
            elif affiliate.approval_status == "rejected":
                alerts.append({"type": "error", "message": "Your affiliate application was rejected.", "action": "profile"})

        return {"status": "success", "data": {"dashboard_type": "affiliate", "alerts": alerts}}

    # Admin / Sub-Admin / Super-Admin
    role_ids = _role_ids_for_user(current_user)
    slugs: set[str] = set()
    if role_ids:
        slugs = {
            p.slug
            for p in db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id.in_(role_ids))
            .filter(Permission.is_active == True)
            .all()
        }

    def _can(*checks: str) -> bool:
        return any(s in slugs for s in checks)

    alerts = []

    pending_users = db.query(User).filter(User.approval_status == "pending").count()
    if pending_users > 0:
        alerts.append({"type": "warning", "message": f"{pending_users} user(s) pending approval", "action": "users"})

    if _can("suppliers.view", "view-suppliers"):
        pending_suppliers = _safe_count(db, Supplier, Supplier.approval_status == "pending")
        if pending_suppliers > 0:
            alerts.append({"type": "warning", "message": f"{pending_suppliers} supplier approval(s) pending", "action": "suppliers"})

    if _can("agents.view", "view-agents"):
        pending_agents = _safe_count(db, Agent, Agent.approval_status == "pending")
        if pending_agents > 0:
            alerts.append({"type": "warning", "message": f"{pending_agents} agent approval(s) pending", "action": "agents"})

    if _can("affiliates.view", "view-affiliates"):
        pending_affiliates = _safe_count(db, Affiliate, Affiliate.approval_status == "pending")
        if pending_affiliates > 0:
            alerts.append({"type": "info", "message": f"{pending_affiliates} affiliate request(s) pending", "action": "affiliates"})

    if _can("payments.view", "view-payments"):
        try:
            failed_payments = db.query(Payment).filter(Payment.payment_status == "failed").count()
            if failed_payments > 0:
                alerts.append({"type": "error", "message": f"{failed_payments} payment failure(s) need review", "action": "payments"})
        except Exception as error:
            logger.warning("Failed to load payment alerts for dashboard: %s", error)

    return {
        "status": "success",
        "data": {
            "dashboard_type": _get_dashboard_type(role_slug),
            "alerts": alerts,
        },
    }


# ---------------------------------------------------------------------------
# Existing analytics endpoints — unchanged
# ---------------------------------------------------------------------------

@router.get("/bookings")
def booking_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_any_permission("dashboard.view", "view-dashboard")),
):
    upcoming = _safe_count(db, Booking, Booking.booking_status == "upcoming")
    ongoing = _safe_count(db, Booking, Booking.booking_status == "ongoing")
    completed = _safe_count(db, Booking, Booking.booking_status == "completed")
    cancelled = _safe_count(db, Booking, Booking.booking_status == "cancelled")

    return {
        "status": "success",
        "data": {
            "filters": _filters_payload(start_date, end_date, country_id),
            "upcoming_bookings": upcoming,
            "ongoing_bookings": ongoing,
            "completed_bookings": completed,
            "cancelled_bookings": cancelled,
            "pending_supplier_acceptance": 0,
        },
    }


@router.get("/revenue")
def revenue_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_any_permission("dashboard.view", "view-dashboard")),
):
    total_revenue = _safe_sum(db, Payment.paid_amount, Payment.payment_status != "refunded")
    paid_amount = _safe_sum(db, Payment.paid_amount, Payment.payment_status == "paid")
    pending_amount = _safe_sum(db, Payment.pending_amount, Payment.payment_status.in_(["pending", "partial"]))
    refunded_amount = _safe_sum(db, Payment.refunded_amount)

    return {
        "status": "success",
        "data": {
            "filters": _filters_payload(start_date, end_date, country_id),
            "total_revenue": total_revenue,
            "monthly_revenue": [],
            "pending_amount": pending_amount,
            "paid_amount": paid_amount,
            "refunded_amount": refunded_amount,
        },
    }


@router.get("/payments")
def payment_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_any_permission("dashboard.view", "view-dashboard")),
):
    return {
        "status": "success",
        "data": {
            "filters": _filters_payload(start_date, end_date, country_id),
            "full_payment_count": _safe_count(db, Payment, Payment.payment_status == "paid"),
            "partial_payment_count": _safe_count(db, Payment, Payment.payment_status == "partial"),
            "pending_payment_count": _safe_count(db, Payment, Payment.payment_status == "pending"),
            "failed_payment_count": _safe_count(db, Payment, Payment.payment_status == "failed"),
            "refunded_payment_count": _safe_count(db, Payment, Payment.payment_status == "refunded"),
        },
    }


@router.get("/reports")
def reports_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_any_permission("dashboard.view", "view-dashboard")),
):
    from sqlalchemy import func
    from app.modules.invoices.models import Invoice

    booking_query = db.query(Booking)
    if country_id:
        booking_query = booking_query.filter(Booking.country_id == country_id)
    total_bookings = booking_query.count()
    paid = db.query(func.coalesce(func.sum(Payment.captured_amount), 0)).filter(Payment.payment_status.notin_(["voided", "failed"])).scalar() or 0
    pending = db.query(func.coalesce(func.sum(Booking.amount_pending), 0)).scalar() or 0
    invoices = db.query(func.count(Invoice.id)).scalar() or 0
    return {
        "status": "success",
        "data": {
            "filters": _filters_payload(start_date, end_date, country_id),
            "total_reports": 4,
            "scheduled_reports": 0,
            "exported_reports": invoices,
            "report_cards": [
                {"name": "Booking Performance", "value": str(total_bookings), "change": "live", "status": "ready"},
                {"name": "Revenue Summary", "value": str(paid), "change": "captured", "status": "ready"},
                {"name": "Payment Pending", "value": str(pending), "change": "open balance", "status": "review"},
                {"name": "Invoices Generated", "value": str(invoices), "change": "generated", "status": "ready"},
            ],
            "recent_exports": [],
        },
    }
