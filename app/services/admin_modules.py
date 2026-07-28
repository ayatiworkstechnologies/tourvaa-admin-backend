from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.admin_modules import AdminModule


def get_admin_modules(db: Session):
    return (
        db.query(AdminModule)
        .filter(AdminModule.is_active == True)
        .order_by(AdminModule.name.asc())
        .all()
    )


def list_all_admin_modules(db: Session):
    return db.query(AdminModule).order_by(AdminModule.name.asc()).all()


def set_admin_module_active(db: Session, module_id: int, is_active: bool) -> AdminModule:
    module = db.query(AdminModule).filter(AdminModule.id == module_id).first()
    if not module:
        raise HTTPException(status_code=404, detail="Admin module not found")
    module.is_active = is_active
    db.commit()
    db.refresh(module)
    return module
