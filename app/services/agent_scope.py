from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.agents import Agent
from app.models.audit import AuditLog
from app.models.bookings import Booking
from app.models.customers import Customer
from app.models.users import User


def is_agent_user(user: User | None) -> bool:
    if not user:
        return False
    role_slugs = set()
    if getattr(user, "role", None) and user.role.slug:
        role_slugs.add(user.role.slug.lower())
    for user_role in getattr(user, "user_roles", None) or []:
        if user_role.role and user_role.role.slug:
            role_slugs.add(user_role.role.slug.lower())
    user_type = str(getattr(user, "user_type", "") or "").lower()
    return (user_type == "agent" or any("agent" in slug for slug in role_slugs)) and not ({"admin", "super-admin"} & role_slugs)


def get_actor_agent(db: Session, user: User) -> Agent:
    agent = db.query(Agent).filter(Agent.user_id == user.id).first()
    if not agent:
        raise HTTPException(status_code=403, detail="Agent profile not found")
    return agent


def agent_customer_filter(db: Session, agent: Agent, actor_user_id: int):
    booked_customer_ids = db.query(Booking.customer_id).filter(Booking.agent_id == agent.id)
    created_customer_ids = db.query(AuditLog.entity_id).filter(
        AuditLog.actor_user_id == actor_user_id,
        AuditLog.action.in_(["create_customer", "link_customer"]),
        AuditLog.entity_type == "customer",
    )
    return or_(Customer.id.in_(booked_customer_ids), Customer.id.in_(created_customer_ids))


def ensure_agent_account_access(db: Session, agent_id: int, user: User | None) -> None:
    if not is_agent_user(user):
        return
    if get_actor_agent(db, user).id != agent_id:
        raise HTTPException(status_code=403, detail="You can only access your own agent account")


def ensure_agent_customer_access(db: Session, customer_id: int, user: User | None) -> None:
    if not is_agent_user(user):
        return
    agent = get_actor_agent(db, user)
    allowed = db.query(Customer.id).filter(
        Customer.id == customer_id,
        agent_customer_filter(db, agent, user.id),
    ).first()
    if not allowed:
        raise HTTPException(status_code=403, detail="Customer access denied")
