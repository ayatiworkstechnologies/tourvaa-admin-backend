from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main  # noqa: F401 - loads every mapped model into Base.metadata
from app.database import Base
from app.models.agents import Agent
from app.models.customers import Customer
from app.models.permissions import Permission, RolePermission
from app.models.roles import Role
from app.models.suppliers import Supplier
from app.models.users import User
from app.routers.dashboard import dashboard_alerts, dashboard_summary


def test_admin_dashboard_counts_profiles_without_duplicate_supplier_approval():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    role = Role(name="Super Admin", slug="super-admin", is_active=True)
    db.add(role)
    db.flush()
    for slug, module in [
        ("view-dashboard", "dashboard"),
        ("view-users", "users"),
        ("view-customers", "customers"),
        ("view-suppliers", "suppliers"),
        ("view-agents", "agents"),
        ("view-bookings", "bookings"),
        ("view-payments", "payments"),
        ("view-tours", "tours"),
    ]:
        permission = Permission(name=slug, slug=slug, module=module, action="get", is_active=True)
        db.add(permission)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))

    admin = User(
        name="Admin",
        email="admin@dashboard.test",
        password="x",
        role_id=role.id,
        user_type="ADMIN",
        is_active=True,
        approval_status="approved",
    )
    customer_user = User(
        name="Customer",
        email="customer@dashboard.test",
        password="x",
        user_type="CUSTOMER",
        is_active=True,
        approval_status="NOT_REQUIRED",
    )
    supplier_user = User(
        name="Supplier",
        email="supplier@dashboard.test",
        password="x",
        user_type="SUPPLIER",
        is_active=True,
        approval_status="PENDING",
    )
    agent_user = User(
        name="Agent",
        email="agent@dashboard.test",
        password="x",
        user_type="AGENT",
        is_active=True,
        approval_status="NOT_REQUIRED",
    )
    db.add_all([admin, customer_user, supplier_user, agent_user])
    db.flush()
    db.add(Customer(user_id=customer_user.id, full_name="Customer", email=customer_user.email))
    db.add(Supplier(user_id=supplier_user.id, supplier_name="Supplier", status="active", approval_status="PENDING"))
    db.add(Agent(user_id=agent_user.id, agent_name="Agent", status="active", approval_status="NOT_REQUIRED"))
    db.commit()
    db.refresh(admin)

    summary = dashboard_summary(
        db=db,
        current_user=admin,
        start_date=None,
        end_date=None,
        country_id=None,
        supplier_id=None,
        agent_id=None,
        booking_status="",
    )["data"]

    assert summary["total_customers"] == 1
    assert summary["total_suppliers"] == 1
    assert summary["pending_suppliers"] == 1
    assert summary["total_agents"] == 1
    assert summary["approved_agents"] == 1
    assert summary["pending_agents"] == 0
    assert summary["active_admin_users"] == 1
    assert summary["pending_admin_users"] == 0

    alerts = dashboard_alerts(db=db, current_user=admin)["data"]["alerts"]
    assert not any("user(s) pending approval" in alert["message"] for alert in alerts)
    assert any("supplier approval(s) pending" in alert["message"] for alert in alerts)

    db.close()
