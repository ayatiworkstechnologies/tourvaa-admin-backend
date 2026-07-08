from sqlalchemy.orm import Session

from app.utils.crypto import decrypt_secret, encrypt_secret
from app.services.audit import log_audit
from app.models.settings import ApiSetting, AppSetting, PaymentSetting
from app.models.users import User

_PAYMENT_SECRET_FIELDS = {"secret_key"}
_API_SECRET_FIELDS = {"api_key", "api_secret"}


DEFAULT_SETTINGS = [
    {"key": "site_name", "label": "Site Name", "value": "Tourvaa", "group": "general", "is_public": True},
    {"key": "company_name", "label": "Company Name", "value": "Tourvaa", "group": "general", "is_public": True},
    {"key": "support_email", "label": "Support Email", "value": "support@tourvaa.com", "group": "general", "is_public": True},
    {"key": "support_phone", "label": "Support Phone", "value": "+910000000000", "group": "general", "is_public": True},
    {"key": "company_address", "label": "Company Address", "value": "New Zealand", "group": "general", "is_public": True},
    {"key": "default_country", "label": "Default Country", "value": "India", "group": "general", "is_public": True},
    {"key": "default_currency", "label": "Default Currency", "value": "INR", "group": "general", "is_public": True},
    {"key": "logo", "label": "Logo URL", "value": "", "group": "general", "is_public": True},
    {"key": "favicon", "label": "Favicon URL", "value": "", "group": "general", "is_public": True},
    {"key": "booking_prefix", "label": "Booking Prefix", "value": "TVA", "group": "booking", "is_public": False},
    {"key": "currency", "label": "Currency", "value": "NZD", "group": "booking", "is_public": True},
    {"key": "timezone", "label": "Timezone", "value": "Pacific/Auckland", "group": "system", "is_public": False},
    {"key": "maintenance_mode", "label": "Maintenance Mode", "value": "false", "group": "system", "is_public": False},
    {"key": "stripe_enabled", "label": "Stripe Enabled", "value": "false", "group": "payment", "is_public": False},
    {"key": "stripe_public_key", "label": "Stripe Public Key", "value": "", "group": "payment", "is_public": False},
    {"key": "stripe_secret_key", "label": "Stripe Secret Key Placeholder", "value": "", "group": "payment", "is_public": False},
    {"key": "paypal_enabled", "label": "PayPal Enabled", "value": "false", "group": "payment", "is_public": False},
    {"key": "paypal_client_id", "label": "PayPal Client ID Placeholder", "value": "", "group": "payment", "is_public": False},
    {"key": "paypal_secret", "label": "PayPal Secret Placeholder", "value": "", "group": "payment", "is_public": False},
    {"key": "payment_surcharge_percentage", "label": "Payment Surcharge Percentage", "value": "0", "group": "payment", "is_public": False},
    {"key": "default_payment_mode", "label": "Default Payment Mode", "value": "test", "group": "payment", "is_public": False},
    {"key": "google_map_api_key", "label": "Google Maps API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "email_api_key", "label": "Email API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "sms_api_key", "label": "SMS API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "third_party_api_key", "label": "Third Party API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "brightlane_external_link", "label": "Brightlane External Link Placeholder", "value": "", "group": "api", "is_public": False},
]

DEFAULT_PAYMENT_SETTINGS = [
    {"provider_name": "stripe", "is_enabled": False, "public_key": "", "secret_key": "", "surcharge_percentage": "0", "mode": "test"},
    {"provider_name": "paypal", "is_enabled": False, "public_key": "", "secret_key": "", "surcharge_percentage": "0", "mode": "test"},
]

DEFAULT_API_SETTINGS = [
    {"api_name": "google_maps", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
    {"api_name": "email_service", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
    {"api_name": "sms_service", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
    {"api_name": "brightlane", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
]


def seed_settings(db: Session):
    for item in DEFAULT_SETTINGS:
        setting = db.query(AppSetting).filter(AppSetting.key == item["key"]).first()

        if not setting:
            db.add(AppSetting(**item))

    db.commit()


def seed_payment_settings(db: Session):
    for item in DEFAULT_PAYMENT_SETTINGS:
        setting = (
            db.query(PaymentSetting)
            .filter(PaymentSetting.provider_name == item["provider_name"])
            .first()
        )

        if not setting:
            db.add(PaymentSetting(**item))

    db.commit()


def seed_api_settings(db: Session):
    for item in DEFAULT_API_SETTINGS:
        setting = db.query(ApiSetting).filter(ApiSetting.api_name == item["api_name"]).first()

        if not setting:
            db.add(ApiSetting(**item))

    db.commit()


def get_settings(db: Session):
    seed_settings(db)
    return db.query(AppSetting).order_by(AppSetting.group.asc(), AppSetting.id.asc()).all()


def get_payment_settings(db: Session):
    seed_payment_settings(db)
    return db.query(PaymentSetting).order_by(PaymentSetting.provider_name.asc()).all()


def get_api_settings(db: Session):
    seed_api_settings(db)
    return db.query(ApiSetting).order_by(ApiSetting.api_name.asc()).all()


def update_payment_setting(
    db: Session,
    provider_name: str,
    values: dict,
    actor: User | None = None,
    request=None,
):
    seed_payment_settings(db)
    setting = (
        db.query(PaymentSetting)
        .filter(PaymentSetting.provider_name == provider_name.strip().lower())
        .first()
    )

    if not setting:
        return None

    old_values = {
        "is_enabled": setting.is_enabled,
        "public_key": setting.public_key,
        "secret_key": setting.secret_key,
        "surcharge_percentage": setting.surcharge_percentage,
        "mode": setting.mode,
    }

    for key, value in values.items():
        if value is not None and hasattr(setting, key):
            v = value.strip() if isinstance(value, str) else value
            setattr(setting, key, encrypt_secret(v) if key in _PAYMENT_SECRET_FIELDS and isinstance(v, str) else v)

    safe_old_values = {k: (mask_secret(v) if k in _PAYMENT_SECRET_FIELDS else v) for k, v in old_values.items()}
    safe_new_values = {k: (mask_secret(v) if k in _PAYMENT_SECRET_FIELDS and isinstance(v, str) else v) for k, v in values.items()}
    log_audit(
        db,
        actor=actor,
        action="update_payment_setting",
        entity_type="payment_setting",
        entity_id=setting.id,
        old_values=safe_old_values,
        new_values=safe_new_values,
        request=request,
    )
    db.commit()
    db.refresh(setting)
    return setting


def update_api_setting(
    db: Session,
    api_name: str,
    values: dict,
    actor: User | None = None,
    request=None,
):
    seed_api_settings(db)
    setting = db.query(ApiSetting).filter(ApiSetting.api_name == api_name.strip().lower()).first()

    if not setting:
        return None

    old_values = {
        "api_key": setting.api_key,
        "api_secret": setting.api_secret,
        "api_url": setting.api_url,
        "is_enabled": setting.is_enabled,
    }

    for key, value in values.items():
        if value is not None and hasattr(setting, key):
            v = value.strip() if isinstance(value, str) else value
            setattr(setting, key, encrypt_secret(v) if key in _API_SECRET_FIELDS and isinstance(v, str) else v)

    safe_old_values = {k: (mask_secret(v) if k in _API_SECRET_FIELDS else v) for k, v in old_values.items()}
    safe_new_values = {k: (mask_secret(v) if k in _API_SECRET_FIELDS and isinstance(v, str) else v) for k, v in values.items()}
    log_audit(
        db,
        actor=actor,
        action="update_api_setting",
        entity_type="api_setting",
        entity_id=setting.id,
        old_values=safe_old_values,
        new_values=safe_new_values,
        request=request,
    )
    db.commit()
    db.refresh(setting)
    return setting


def update_settings(
    db: Session,
    values: dict[str, str | None],
    actor: User | None = None,
    request=None,
):
    seed_settings(db)
    old_values = {
        setting.key: setting.value
        for setting in db.query(AppSetting).filter(AppSetting.key.in_(values.keys())).all()
    }

    for key, value in values.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()

        if setting:
            setting.value = value

    log_audit(
        db,
        actor=actor,
        action="update_settings",
        entity_type="settings",
        old_values=old_values,
        new_values=values,
        request=request,
    )
    db.commit()
    return get_settings(db)


SYSTEM_SETTING_KEYS = [
    "site_name",
    "company_name",
    "support_email",
    "support_phone",
    "default_country",
    "default_currency",
    "timezone",
    "logo",
    "favicon",
    "maintenance_mode",
]


def _settings_dict(settings_rows):
    return {row.key: row.value for row in settings_rows}


def mask_secret(value: str | None):
    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{value[:7]}************"


def get_system_settings(db: Session):
    rows = get_settings(db)
    values = _settings_dict(rows)
    return {key: values.get(key) for key in SYSTEM_SETTING_KEYS}


def update_system_settings(
    db: Session,
    values: dict[str, str | bool | None],
    actor: User | None = None,
    request=None,
):
    normalized = {}
    for key, value in values.items():
        if key not in SYSTEM_SETTING_KEYS or value is None:
            continue
        if isinstance(value, bool):
            normalized[key] = "true" if value else "false"
        else:
            normalized[key] = value.strip() if isinstance(value, str) else value

    if normalized:
        update_settings(db, normalized, actor=actor, request=request)

    return get_system_settings(db)


def get_payment_settings_payload(db: Session):
    rows = {item.provider_name: item for item in get_payment_settings(db)}
    stripe = rows.get("stripe")
    paypal = rows.get("paypal")
    surcharge = "0"

    if stripe:
        surcharge = stripe.surcharge_percentage
    elif paypal:
        surcharge = paypal.surcharge_percentage

    stripe_secret = decrypt_secret(stripe.secret_key if stripe else "")
    paypal_secret = decrypt_secret(paypal.secret_key if paypal else "")
    return {
        "stripe_enabled": stripe.is_enabled if stripe else False,
        "stripe_public_key": stripe.public_key if stripe else "",
        "stripe_secret_key": mask_secret(stripe_secret),
        "stripe_secret_placeholder": mask_secret(stripe_secret),
        "paypal_enabled": paypal.is_enabled if paypal else False,
        "paypal_client_id": paypal.public_key if paypal else "",
        "paypal_client_id_placeholder": paypal.public_key if paypal else "",
        "paypal_secret": mask_secret(paypal_secret),
        "paypal_secret_placeholder": mask_secret(paypal_secret),
        "payment_surcharge_percentage": surcharge,
        "default_payment_mode": stripe.mode if stripe else (paypal.mode if paypal else "test"),
    }


def update_payment_settings_payload(
    db: Session,
    values: dict[str, str | bool | None],
    actor: User | None = None,
    request=None,
):
    stripe_values = {}
    paypal_values = {}

    if values.get("stripe_enabled") is not None:
        stripe_values["is_enabled"] = values["stripe_enabled"]
    if values.get("stripe_public_key") is not None:
        stripe_values["public_key"] = values["stripe_public_key"]
    if values.get("stripe_secret_key") is not None:
        stripe_values["secret_key"] = values["stripe_secret_key"]
    if values.get("stripe_secret_placeholder") is not None:
        stripe_values["secret_key"] = values["stripe_secret_placeholder"]

    if values.get("paypal_enabled") is not None:
        paypal_values["is_enabled"] = values["paypal_enabled"]
    if values.get("paypal_client_id") is not None:
        paypal_values["public_key"] = values["paypal_client_id"]
    if values.get("paypal_client_id_placeholder") is not None:
        paypal_values["public_key"] = values["paypal_client_id_placeholder"]
    if values.get("paypal_secret") is not None:
        paypal_values["secret_key"] = values["paypal_secret"]
    if values.get("paypal_secret_placeholder") is not None:
        paypal_values["secret_key"] = values["paypal_secret_placeholder"]

    if values.get("payment_surcharge_percentage") is not None:
        surcharge = values["payment_surcharge_percentage"]
        stripe_values["surcharge_percentage"] = surcharge
        paypal_values["surcharge_percentage"] = surcharge
    if values.get("default_payment_mode") is not None:
        stripe_values["mode"] = values["default_payment_mode"]
        paypal_values["mode"] = values["default_payment_mode"]

    if stripe_values:
        update_payment_setting(db, "stripe", stripe_values, actor=actor, request=request)
    if paypal_values:
        update_payment_setting(db, "paypal", paypal_values, actor=actor, request=request)

    return get_payment_settings_payload(db)


def get_api_settings_payload(db: Session):
    rows = {item.api_name: item for item in get_api_settings(db)}
    google_maps = rows.get("google_maps")
    email_service = rows.get("email_service")
    sms_service = rows.get("sms_service")
    brightlane = rows.get("brightlane")

    gm_key = decrypt_secret(google_maps.api_key if google_maps else "")
    em_key = decrypt_secret(email_service.api_key if email_service else "")
    sms_key = decrypt_secret(sms_service.api_key if sms_service else "")
    return {
        "google_map_api_key": mask_secret(gm_key),
        "google_maps_api_placeholder": mask_secret(gm_key),
        "email_api_key": mask_secret(em_key),
        "email_api_placeholder": mask_secret(em_key),
        "sms_api_key": mask_secret(sms_key),
        "sms_api_placeholder": mask_secret(sms_key),
        "brightlane_external_link": brightlane.api_url if brightlane else "",
        "brightlane_external_link_placeholder": brightlane.api_url if brightlane else "",
    }


def update_api_settings_payload(
    db: Session,
    values: dict[str, str | bool | None],
    actor: User | None = None,
    request=None,
):
    mappings = {
        "google_map_api_key": ("google_maps", "api_key"),
        "google_maps_api_placeholder": ("google_maps", "api_key"),
        "email_api_key": ("email_service", "api_key"),
        "email_api_placeholder": ("email_service", "api_key"),
        "sms_api_key": ("sms_service", "api_key"),
        "sms_api_placeholder": ("sms_service", "api_key"),
        "brightlane_external_link": ("brightlane", "api_url"),
        "brightlane_external_link_placeholder": ("brightlane", "api_url"),
    }

    updates_by_api = {}
    for field, value in values.items():
        if value is None or field not in mappings:
            continue
        api_name, api_field = mappings[field]
        updates_by_api.setdefault(api_name, {})[api_field] = value

    for api_name, update_values in updates_by_api.items():
        update_api_setting(db, api_name, update_values, actor=actor, request=request)

    return get_api_settings_payload(db)
