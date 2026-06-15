from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.email_templates.models import EmailTemplate
from app.modules.email_templates.schemas import EmailTemplateCreate, EmailTemplateUpdate


DEFAULT_EMAIL_TEMPLATES = [
    {
        "key": "registration_pending",
        "name": "Registration Pending",
        "subject": "Tourvaa registration received",
        "body": (
            "Your Tourvaa registration is received and waiting for admin approval.\n\n"
            "Name: {{name}}\n"
            "Email: {{email}}\n"
            "Phone: {{phone}}\n"
            "Requested role: {{role_name}}"
        ),
    },
    {
        "key": "account_approved",
        "name": "Account Approved",
        "subject": "Your Tourvaa account is approved",
        "body": "Hi {{name}}, your Tourvaa account is approved. Login here: {{login_url}}",
    },
    {
        "key": "user_created",
        "name": "User Created",
        "subject": "Your Tourvaa account is ready",
        "body": "Hi {{name}}, your account was created. Email: {{email}} Password: {{password}}",
    },
    {
        "key": "password_reset",
        "name": "Password Reset",
        "subject": "Reset your Tourvaa password",
        "body": "We received a password reset request. Use this secure link within 30 minutes: {{reset_url}}",
    },
    {
        "key": "password_changed",
        "name": "Password Changed",
        "subject": "Your Tourvaa password was changed",
        "body": "Your password was changed successfully. You can now login here: {{login_url}}",
    },
]


def seed_email_templates(db: Session):
    for item in DEFAULT_EMAIL_TEMPLATES:
        template = db.query(EmailTemplate).filter(EmailTemplate.key == item["key"]).first()

        if not template:
            db.add(EmailTemplate(**item, is_active=True))

    db.commit()


def get_templates(db: Session, page: int | None = None, limit: int | None = None, search: str = ""):
    seed_email_templates(db)
    query = db.query(EmailTemplate)

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                EmailTemplate.key.ilike(pattern),
                EmailTemplate.name.ilike(pattern),
                EmailTemplate.subject.ilike(pattern),
            )
        )

    query = query.order_by(EmailTemplate.id.desc())

    if page is None or limit is None:
        return query.all()

    total = query.count()
    items = query.offset((page - 1) * limit).limit(limit).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


def get_template(db: Session, template_id: int):
    template = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Email template not found")

    return template


def create_template(db: Session, data: EmailTemplateCreate):
    existing = db.query(EmailTemplate).filter(EmailTemplate.key == data.key).first()

    if existing:
        raise HTTPException(status_code=400, detail="Template key already exists")

    template = EmailTemplate(**data.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def update_template(db: Session, template_id: int, data: EmailTemplateUpdate):
    template = get_template(db, template_id)

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(template, key, value)

    db.commit()
    db.refresh(template)
    return template


def delete_template(db: Session, template_id: int):
    template = get_template(db, template_id)
    db.delete(template)
    db.commit()
    return True
