from sqlalchemy.orm import Session

from app.modules.admin_modules.models import AdminModule


def get_admin_modules(db: Session):
    return (
        db.query(AdminModule)
        .filter(AdminModule.is_active == True)
        .order_by(AdminModule.name.asc())
        .all()
    )
