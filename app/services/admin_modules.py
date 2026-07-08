from sqlalchemy.orm import Session

from app.models.admin_modules import AdminModule


def get_admin_modules(db: Session):
    return (
        db.query(AdminModule)
        .filter(AdminModule.is_active == True)
        .order_by(AdminModule.name.asc())
        .all()
    )
