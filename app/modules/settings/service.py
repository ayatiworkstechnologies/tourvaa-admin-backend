from sqlalchemy.orm import Session

from app.modules.settings.models import AppSetting


DEFAULT_SETTINGS = [
    {"key": "site_name", "label": "Site Name", "value": "Tourvaa", "group": "general", "is_public": True},
    {"key": "support_email", "label": "Support Email", "value": "support@tourvaa.com", "group": "general", "is_public": True},
    {"key": "support_phone", "label": "Support Phone", "value": "+64 000 000 000", "group": "general", "is_public": True},
    {"key": "company_address", "label": "Company Address", "value": "New Zealand", "group": "general", "is_public": True},
    {"key": "booking_prefix", "label": "Booking Prefix", "value": "TVA", "group": "booking", "is_public": False},
    {"key": "currency", "label": "Currency", "value": "NZD", "group": "booking", "is_public": True},
    {"key": "timezone", "label": "Timezone", "value": "Pacific/Auckland", "group": "system", "is_public": False},
    {"key": "maintenance_mode", "label": "Maintenance Mode", "value": "false", "group": "system", "is_public": False},
]


def seed_settings(db: Session):
    for item in DEFAULT_SETTINGS:
        setting = db.query(AppSetting).filter(AppSetting.key == item["key"]).first()

        if not setting:
            db.add(AppSetting(**item))

    db.commit()


def get_settings(db: Session):
    seed_settings(db)
    return db.query(AppSetting).order_by(AppSetting.group.asc(), AppSetting.id.asc()).all()


def update_settings(db: Session, values: dict[str, str | None]):
    seed_settings(db)

    for key, value in values.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()

        if setting:
            setting.value = value

    db.commit()
    return get_settings(db)
