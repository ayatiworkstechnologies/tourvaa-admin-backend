from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_permission
from app.modules.email_templates.schemas import EmailTemplateCreate, EmailTemplateUpdate
from app.modules.email_templates.service import (
    create_template,
    delete_template,
    get_template,
    get_templates,
    update_template,
)

router = APIRouter(prefix="/email-templates", tags=["Email Templates"])


@router.get("/")
def list_templates(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-email")),
):
    return {"status": "success", "data": get_templates(db)}


@router.get("/{template_id}")
def detail_template(
    template_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-email")),
):
    return {"status": "success", "data": get_template(db, template_id)}


@router.post("/")
def add_template(
    data: EmailTemplateCreate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("create-email")),
):
    return {
        "status": "success",
        "message": "Email template created successfully",
        "data": create_template(db, data),
    }


@router.put("/{template_id}")
def edit_template(
    template_id: int,
    data: EmailTemplateUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("update-email")),
):
    return {
        "status": "success",
        "message": "Email template updated successfully",
        "data": update_template(db, template_id, data),
    }


@router.delete("/{template_id}")
def remove_template(
    template_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("delete-email")),
):
    delete_template(db, template_id)
    return {"status": "success", "message": "Email template deleted successfully"}
