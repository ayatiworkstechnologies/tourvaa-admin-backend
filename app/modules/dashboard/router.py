from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.audit.models import AuditLog
from app.modules.common.auth import get_current_user, require_permission
from app.modules.users.models import User
from app.modules.roles.models import Role
from app.modules.permissions.models import Permission, RolePermission
from app.modules.users.models import UserRole
from app.modules.common.media import existing_storage_path

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


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
    role_ids.update(user_role.role_id for user_role in user.user_roles)
    return [role_id for role_id in role_ids if role_id]


def get_dashboard_menus(permissions):
    menu_map = {
        "view-dashboard": "Dashboard",
        "view-users": "Users",
        "view-roles": "Roles",
        "view-permissions": "Permissions",
        "view-suppliers": "Suppliers",
        "view-agents": "Agents",
        "view-resellers": "Resellers",
        "view-customers": "Customers",
        "view-tours": "Tours",
        "view-bookings": "Bookings",
        "view-payments": "Payments",
        "view-reports": "Reports",
        "view-email": "Email Templates",
        "view-settings": "Settings",
        "view-profile": "Profile",
    }

    menus = []

    for permission in permissions:
        if permission.slug in menu_map:
            menus.append({
                "label": menu_map[permission.slug],
                "permission": permission.slug,
                "module": permission.module,
            })

    return menus


@router.get("/me")
def my_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    role_ids = _role_ids_for_user(current_user)
    permissions = []

    if role_ids:
        permissions = (
            db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id.in_(role_ids))
            .filter(Permission.is_active == True)
            .distinct()
            .all()
        )

    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    pending_users = db.query(User).filter(User.approval_status == "pending").count()
    total_roles = db.query(Role).filter(Role.is_active == True).count()
    permission_slugs = {permission.slug for permission in permissions}

    can_view_users = "view-users" in permission_slugs
    can_manage_users = can_view_users or "update-users" in permission_slugs
    can_view_roles = "view-roles" in permission_slugs
    pending_approval_users = []

    if can_manage_users:
        pending_approval_users = (
            db.query(User)
            .filter(User.approval_status == "pending")
            .order_by(User.id.desc())
            .limit(5)
            .all()
        )

    return {
        "status": "success",
        "data": {
            "user": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
                "profile_image": existing_storage_path(current_user.profile_image),
                "role": {
                    "id": current_user.role.id if current_user.role else None,
                    "name": current_user.role.name if current_user.role else None,
                    "slug": current_user.role.slug if current_user.role else None,
                }
            },
            "permissions": [
                {
                    "name": permission.name,
                    "slug": permission.slug,
                    "module": permission.module,
                    "action": permission.action,
                }
                for permission in permissions
            ],
            "menus": get_dashboard_menus(permissions),
            "stats": {
                "users": total_users if can_view_users else 0,
                "active_users": active_users if can_view_users else 0,
                "roles": total_roles if can_view_roles else 0,
                "permissions": len(permissions),
                "pending_users": pending_users if can_manage_users else 0,
            },
            "pending_approvals": [
                {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role_id": user.role_id,
                    "role_name": user.role.name if user.role else None,
                    "created_at": user.created_at,
                }
                for user in pending_approval_users
            ],
        }
    }


@router.get("/summary")
def dashboard_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_permission("view-dashboard")),
):
    total_users = db.query(User).count()
    pending_users = db.query(User).filter(User.approval_status == "pending").count()
    active_users = db.query(User).filter(User.is_active == True).count()

    return {
        "status": "success",
        "data": {
            "filters": _filters_payload(start_date, end_date, country_id),
            "total_bookings": 0,
            "total_customers": total_users,
            "total_suppliers": 0,
            "approved_suppliers": 0,
            "pending_suppliers": 0,
            "total_agents": 0,
            "approved_agents": 0,
            "pending_agents": 0,
            "active_admin_users": active_users,
            "pending_admin_users": pending_users,
            "total_revenue": 0,
            "pending_payments": 0,
            "upcoming_bookings": 0,
        },
    }


@router.get("/bookings")
def booking_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    _current_user: User = Depends(require_permission("view-dashboard")),
):
    return {
        "status": "success",
        "data": {
            "filters": _filters_payload(start_date, end_date, country_id),
            "upcoming_bookings": 0,
            "ongoing_bookings": 0,
            "completed_bookings": 0,
            "cancelled_bookings": 0,
            "pending_supplier_acceptance": 0,
        },
    }


@router.get("/revenue")
def revenue_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    _current_user: User = Depends(require_permission("view-dashboard")),
):
    return {
        "status": "success",
        "data": {
            "filters": _filters_payload(start_date, end_date, country_id),
            "total_revenue": 0,
            "monthly_revenue": [],
            "pending_amount": 0,
            "paid_amount": 0,
            "refunded_amount": 0,
        },
    }


@router.get("/payments")
def payment_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    _current_user: User = Depends(require_permission("view-dashboard")),
):
    return {
        "status": "success",
        "data": {
            "filters": _filters_payload(start_date, end_date, country_id),
            "full_payment_count": 0,
            "partial_payment_count": 0,
            "pending_payment_count": 0,
            "failed_payment_count": 0,
            "refunded_payment_count": 0,
        },
    }


@router.get("/reports")
def reports_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country_id: int | None = Query(default=None),
    _current_user: User = Depends(require_permission("view-dashboard")),
):
    return {
        "status": "success",
        "data": {
            "filters": _filters_payload(start_date, end_date, country_id),
            "total_reports": 6,
            "scheduled_reports": 3,
            "exported_reports": 18,
            "report_cards": [
                {"name": "Booking Performance", "value": "128", "change": "+12%", "status": "ready"},
                {"name": "Revenue Summary", "value": "₹4.8L", "change": "+8%", "status": "ready"},
                {"name": "Supplier Approval", "value": "14", "change": "5 pending", "status": "review"},
                {"name": "Agent Sales", "value": "36", "change": "+6%", "status": "ready"},
                {"name": "Payment Collection", "value": "92%", "change": "8% pending", "status": "review"},
                {"name": "Country-wise Bookings", "value": "9", "change": "countries", "status": "ready"},
            ],
            "recent_exports": [
                {"id": 1, "name": "Monthly Booking Report", "format": "XLSX", "generated_at": "2026-06-15 09:30"},
                {"id": 2, "name": "Supplier Pending Approval", "format": "PDF", "generated_at": "2026-06-14 17:10"},
                {"id": 3, "name": "Payment Collection Summary", "format": "CSV", "generated_at": "2026-06-14 11:45"},
            ],
        },
    }


@router.get("/recent-activities")
def recent_activities(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_permission("view-dashboard")),
):
    admin_actions = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(10)
        .all()
    )

    return {
        "status": "success",
        "data": {
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
