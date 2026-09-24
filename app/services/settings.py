from sqlalchemy.orm import Session

from app.utils.crypto import decrypt_secret, encrypt_secret
from app.services.audit import log_audit
from app.models.settings import ApiSetting, AppSetting, PaymentSetting, SmtpSetting
from app.models.users import User

_PAYMENT_SECRET_FIELDS = {"secret_key"}
_API_SECRET_FIELDS = {"api_key", "api_secret"}
_SMTP_SECRET_FIELDS = {"password"}

SUPPORTED_TIMEZONES = {
    "Pacific/Auckland", "Pacific/Fiji", "Australia/Sydney", "Australia/Perth",
    "Asia/Tokyo", "Asia/Singapore", "Asia/Kolkata", "Asia/Dubai", "Asia/Karachi",
    "Asia/Dhaka", "Asia/Bangkok", "Asia/Shanghai", "Asia/Hong_Kong", "Europe/London",
    "Europe/Paris", "Europe/Berlin", "Europe/Istanbul", "Africa/Johannesburg",
    "Africa/Nairobi", "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "America/Toronto", "America/Sao_Paulo", "UTC",
}

# Values that may already exist from the old free-text timezone field.
# Normalize them on the next settings save instead of rejecting the entire
# bulk update request.
LEGACY_TIMEZONE_ALIASES = {
    "india": "Asia/Kolkata",
    "ist": "Asia/Kolkata",
    "new zealand": "Pacific/Auckland",
    "nzst": "Pacific/Auckland",
    "auckland": "Pacific/Auckland",
    "utc": "UTC",
    "gmt": "UTC",
}


def normalize_timezone_name(value: str | None) -> str:
    timezone_name = (value or "").strip()
    return LEGACY_TIMEZONE_ALIASES.get(timezone_name.lower(), timezone_name)

_PLACEHOLDER_PUBLIC_CONTACTS = {
    "support_email": {"hello@tourvaa.com", "support@tourvaa.com"},
    "support_phone": {"+910000000000", "+919876543210"},
    "company_address": {"new zealand"},
}

_PUBLIC_TEXT_LIMITS = {
    "site_name": 80,
    "app_name": 80,
    "company_name": 120,
    "site_tagline": 240,
    "footer_description": 500,
}

_UNSAFE_PUBLIC_TEXT_MARKERS = (
    "<script",
    "</script",
    "javascript:",
    "document.",
    "window.",
    "innerhtml",
    "onerror=",
    "onload=",
)


def sanitize_public_contact_setting(key: str, value: str | None) -> str:
    normalized = (value or "").strip()
    if normalized.lower() in _PLACEHOLDER_PUBLIC_CONTACTS.get(key, set()):
        return ""
    return normalized


def sanitize_public_setting(key: str, value: str | None) -> str:
    """Keep compromised or malformed CMS text out of public page chrome.

    React escapes text values, but a stored script payload can still destroy
    the layout when it is displayed as a site name or footer description.
    Public text fields therefore have conservative length and content checks.
    """
    normalized = sanitize_public_contact_setting(key, value)
    limit = _PUBLIC_TEXT_LIMITS.get(key)
    if limit is None:
        return normalized
    lowered = normalized.lower()
    if len(normalized) > limit or any(marker in lowered for marker in _UNSAFE_PUBLIC_TEXT_MARKERS):
        return ""
    return normalized


DEFAULT_SETTINGS = [
    {"key": "site_name", "label": "Site Name", "value": "Tourvaa", "group": "general", "is_public": True},
    {"key": "company_name", "label": "Company Name", "value": "Tourvaa", "group": "general", "is_public": True},
    {"key": "support_email", "label": "Support Email", "value": "", "group": "general", "is_public": True},
    {"key": "support_phone", "label": "Support Phone", "value": "", "group": "general", "is_public": True},
    {"key": "company_address", "label": "Company Address", "value": "", "group": "general", "is_public": True},
    {"key": "default_country", "label": "Default Country", "value": "India", "group": "general", "is_public": True},
    {"key": "default_currency", "label": "Default Currency", "value": "USD", "group": "general", "is_public": True},
    {"key": "logo", "label": "Logo URL", "value": "", "group": "general", "is_public": True},
    {"key": "favicon", "label": "Favicon URL", "value": "", "group": "general", "is_public": True},
    {"key": "booking_prefix", "label": "Booking Prefix", "value": "TVA", "group": "booking", "is_public": False},
    # Admin-configured MINIMUM supplier commission percentage -- UI label is
    # "Default Tourvaa Commission" (this is the ONLY commission Tourvaa
    # itself earns; agent/affiliate commission below is carved out of it,
    # never paid additionally -- see services.bookings._apply_commission_snapshot).
    # A supplier's own commission_percentage (suppliers.commission_percentage)
    # may be set higher than this at onboarding/approval or raised later by
    # the supplier, but a write can never take it below the current value of
    # this setting. When a supplier has no rate of their own, this value is
    # used directly. See services.settings.get_commission_percentage and
    # services.bookings.supplier_accept_booking (the ledger commission calc).
    # Moved to the "pricing" group (was "booking") per the Pricing & Commission
    # / Booking Rules settings-screen split.
    {"key": "supplier_commission_percentage", "label": "Default Tourvaa Commission (%)", "value": "10", "group": "pricing", "is_public": True},
    {"key": "default_admin_markup_percentage", "label": "Default Admin Markup (%)", "value": "0", "group": "pricing", "is_public": False},
    # Platform-wide fallback deposit percentage, used only when a tour has no
    # deposit_percentage/booking_deposit of its own set (Tour.deposit_type
    # etc. - see models/cms.py). A supplier's own per-tour deposit config
    # always takes priority over this. See get_default_deposit_percentage.
    # Group "booking_rules" (was "booking") -- pricing/commission settings
    # and booking-behavior settings are now separate settings-screen sections.
    {"key": "default_deposit_percentage", "label": "Default Deposit Percentage (%)", "value": "20", "group": "booking_rules", "is_public": True},
    # Platform-wide fallback for how many days before departure a deposit is
    # still offered (Tour.deposit_cutoff_days) and how many days before
    # departure the remaining balance is due (Tour.balance_payment_deadline_days).
    # Same fallback-only role as default_deposit_percentage above - a tour's
    # own values always take priority.
    {"key": "default_deposit_cutoff_days", "label": "Default Deposit Cutoff (days before departure)", "value": "30", "group": "booking_rules", "is_public": True},
    {"key": "default_balance_payment_deadline_days", "label": "Default Final Payment Due (days before departure)", "value": "14", "group": "booking_rules", "is_public": True},
    # Admin-configured MAXIMUM commission Tourvaa pays out to an agent or
    # affiliate. Unlike the supplier minimum above, agent/affiliate
    # commission flows the other way (Tourvaa pays them, carved out of its
    # own commission -- never additional), so the admin control here is a
    # ceiling, not a floor - see get_agent_commission_max /
    # get_affiliate_commission_max and their write-path enforcement in
    # services.agents.update_agent_discount and the affiliate commission
    # rate/rule write paths. Lowered from 20% to 5% -- the prior default let
    # an agent/affiliate rate approach or exceed Tourvaa's own default 10%
    # commission, which the commission-deduction model treats as an error
    # (see _apply_commission_snapshot's <= validation).
    {"key": "agent_commission_max_percentage", "label": "Maximum Agent Commission (%)", "value": "5", "group": "pricing", "is_public": True},
    {"key": "affiliate_commission_max_percentage", "label": "Maximum Affiliate Commission (%)", "value": "5", "group": "pricing", "is_public": True},
    # Default commission % shown to a new agent on the post-login
    # commission-consent popup (see CommissionConsentModal) - unlike the
    # supplier minimum above, agents have no per-record override today, so
    # this is the only rate an agent is ever shown/accepts. Lowered from 10%
    # to 3% to match the commission-deduction business model (agent
    # commission is carved out of Tourvaa's own ~10% commission, so 10%
    # would leave Tourvaa with nothing).
    {"key": "agent_default_commission_percentage", "label": "Default Agent Commission (%)", "value": "3", "group": "pricing", "is_public": True},
    # Whether an agent may additionally set their own retail markup on top
    # of the storefront price (see services.bookings.create_booking /
    # calculate_booking_price, where agent_markup is currently always forced
    # to 0). Recommended/default OFF -- agents already earn a platform-paid
    # commission; combining both requires deliberate admin opt-in so
    # agent_markup_amount and agent_commission_amount are never silently
    # mixed. Turning this ON without also updating create_booking/
    # calculate_booking_price to read it is a no-op; see the TODO there.
    {"key": "allow_agent_markup", "label": "Allow Agent Markup", "value": "false", "group": "pricing", "is_public": False},
    # Whether the SAME booking may pay commission to both an agent and an
    # affiliate. Recommended/default OFF: an agent booking should only ever
    # pay agent commission, and a direct customer booking attributed to an
    # affiliate should only ever pay affiliate commission -- otherwise
    # Tourvaa's own commission (the only pool either is paid from) can be
    # split three ways and go negative. Enforced in
    # services.bookings.supplier_accept_booking, which skips affiliate
    # conversion recording for an agent-sourced booking unless this is "true".
    {"key": "allow_agent_and_affiliate_commission_same_booking", "label": "Allow Agent + Affiliate Commission on Same Booking", "value": "false", "group": "pricing", "is_public": False},
    {"key": "currency", "label": "Currency", "value": "USD", "group": "booking", "is_public": True},
    # This ONLY controls whether "currency" above locks the display currency
    # for every site visitor (frontend useCurrency.ts) - it must default to
    # "false", since "currency" itself always has a non-blank value (it also
    # doubles as the default booking/tour currency) and the admin UI's
    # CurrencySelect has no blank option, so without this separate opt-in
    # every fresh install would silently force-lock the currency selector
    # for all visitors with no way to turn it back off.
    {"key": "force_site_currency", "label": "Force Currency For All Visitors", "value": "false", "group": "booking", "is_public": True},
    {"key": "timezone", "label": "Timezone", "value": "Pacific/Auckland", "group": "system", "is_public": False},
    {"key": "maintenance_mode", "label": "Maintenance Mode", "value": "false", "group": "system", "is_public": False},
    # DEPRECATED and no longer seeded: stripe_enabled/stripe_public_key/
    # stripe_secret_key/paypal_enabled/paypal_client_id/paypal_secret/
    # default_payment_mode used to duplicate what PaymentSetting (see
    # DEFAULT_PAYMENT_SETTINGS below) already stores -- grepping the
    # codebase found these AppSetting keys were never read anywhere, only
    # ever written by this seed list. PaymentSetting is the one real source
    # for Stripe/PayPal config; removed from here so a fresh install doesn't
    # create dead duplicate rows. Any pre-existing rows in an already-seeded
    # database are harmless leftovers, not cleaned up automatically.
    {"key": "payment_surcharge_percentage", "label": "Payment Surcharge Percentage", "value": "0", "group": "payment", "is_public": False},
    {"key": "google_map_api_key", "label": "Google Maps API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "email_api_key", "label": "Email API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "sms_api_key", "label": "SMS API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "third_party_api_key", "label": "Third Party API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "brightlane_external_link", "label": "Brightlane External Link Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "affiliate_default_commission_type", "label": "Default Affiliate Commission Type", "value": "percentage", "group": "affiliate", "is_public": False},
    # Public so the post-login commission-consent popup (CommissionConsentModal)
    # can read it via GET /settings/public before an affiliate is approved,
    # the same way suppliers already read supplier_commission_percentage.
    # Lowered from 5% to 3% -- same reasoning as agent_default_commission_percentage
    # above: affiliate commission is carved out of Tourvaa's own ~10%
    # commission, not paid additionally.
    {"key": "affiliate_default_commission_value", "label": "Default Affiliate Commission Value", "value": "3", "group": "affiliate", "is_public": True},
    {"key": "affiliate_default_attribution_model", "label": "Default Attribution Model", "value": "last_click", "group": "affiliate", "is_public": False},
    {"key": "affiliate_default_attribution_window_days", "label": "Default Attribution Window (days)", "value": "30", "group": "affiliate", "is_public": False},
    {"key": "affiliate_minimum_payout", "label": "Minimum Affiliate Payout", "value": "50", "group": "affiliate", "is_public": False},
    {"key": "affiliate_allow_self_link_creation", "label": "Allow Affiliate Self-Service Link Creation", "value": "true", "group": "affiliate", "is_public": False},
    {"key": "affiliate_allow_custom_alias", "label": "Allow Custom Alias", "value": "true", "group": "affiliate", "is_public": False},
    {"key": "affiliate_auto_approve_commission", "label": "Auto-Approve Affiliate Commission", "value": "false", "group": "affiliate", "is_public": False},
    # Documents the rounding behavior services.bookings.money() already
    # implements (Decimal, 2 places, ROUND_HALF_UP) -- exposed as a setting
    # so it's discoverable/auditable rather than only implicit in code.
    # Changing these values does NOT currently change money()'s actual
    # behavior; they're documentation-only until a caller reads them.
    {"key": "money_decimal_places", "label": "Money Decimal Places (informational only, fixed at 2)", "value": "2", "group": "system", "is_public": False},
    {"key": "money_rounding_method", "label": "Money Rounding Method (informational only, fixed at HALF_UP)", "value": "HALF_UP", "group": "system", "is_public": False},
    # Granular first-login/setup-wizard progress flags (replaces a single
    # initial_setup_completed boolean) so the admin dashboard can show
    # "Platform Setup: 5/7 complete" instead of an all-or-nothing state.
    {"key": "company_setup_completed", "label": "Company Setup Completed", "value": "false", "group": "system", "is_public": False},
    {"key": "pricing_setup_completed", "label": "Pricing Setup Completed", "value": "false", "group": "system", "is_public": False},
    {"key": "booking_rules_completed", "label": "Booking Rules Setup Completed", "value": "false", "group": "system", "is_public": False},
    {"key": "payment_setup_completed", "label": "Payment Setup Completed", "value": "false", "group": "system", "is_public": False},
    {"key": "email_setup_completed", "label": "Email Setup Completed", "value": "false", "group": "system", "is_public": False},
    {"key": "storage_setup_completed", "label": "Storage Setup Completed", "value": "false", "group": "system", "is_public": False},
    {"key": "security_check_completed", "label": "Security Check Completed", "value": "false", "group": "system", "is_public": False},
]

# Steps tracked by the Platform Setup checklist (see get_setup_progress) --
# each key must exist in DEFAULT_SETTINGS above with value "true"/"false".
SETUP_CHECKLIST_KEYS = [
    "company_setup_completed",
    "pricing_setup_completed",
    "booking_rules_completed",
    "payment_setup_completed",
    "email_setup_completed",
    "storage_setup_completed",
    "security_check_completed",
]


def _setup_checks(db: Session) -> dict[str, list[tuple[str, bool]]]:
    """Real configuration checks behind each Platform Setup step. A step is
    only complete when every one of its checks passes, so the checklist
    can't report "ready" just because someone flipped a flag."""
    from app.config import settings as app_settings
    from app.models.bookings import EmailLog

    values = {s.key: (s.value or "").strip() for s in db.query(AppSetting).all()}

    def _num(key: str):
        try:
            return float(values.get(key, ""))
        except (TypeError, ValueError):
            return None

    tourvaa = _num("supplier_commission_percentage")
    agent_default = _num("agent_default_commission_percentage")
    agent_max = _num("agent_commission_max_percentage")
    deposit = _num("default_deposit_percentage")
    cutoff = _num("default_deposit_cutoff_days")
    balance_days = _num("default_balance_payment_deadline_days")

    gateways = db.query(PaymentSetting).filter(PaymentSetting.is_enabled.is_(True)).all()
    webhook_for = {
        "stripe": bool((app_settings.STRIPE_WEBHOOK_SECRET or "").strip()),
        "paypal": bool((app_settings.PAYPAL_WEBHOOK_ID or "").strip()),
    }
    smtp = db.query(SmtpSetting).filter(SmtpSetting.is_enabled.is_(True)).first()
    smtp_configured = bool((smtp and (smtp.host or "").strip()) or (getattr(app_settings, "SMTP_HOST", "") or "").strip())
    email_delivered = db.query(EmailLog.id).filter(EmailLog.status == "sent").first() is not None

    import os
    try:
        workers = int(os.environ.get("WEB_CONCURRENCY", "1") or "1")
    except ValueError:
        workers = 1

    def _le(a, b):
        return a is not None and b is not None and a <= b

    return {
        "company_setup_completed": [
            ("Site name set", bool(values.get("site_name"))),
            ("Support email set", bool(values.get("support_email"))),
            ("Company address set", bool(values.get("company_address"))),
        ],
        "pricing_setup_completed": [
            ("Tourvaa commission configured", tourvaa is not None and 0 < tourvaa < 100),
            ("Agent default <= agent maximum <= Tourvaa commission", _le(agent_default, agent_max) and _le(agent_max, tourvaa)),
        ],
        "booking_rules_completed": [
            ("Deposit percentage between 1 and 100", deposit is not None and 0 < deposit <= 100),
            ("Balance due before the deposit cutoff", cutoff is not None and balance_days is not None and 0 <= balance_days <= cutoff),
            ("Booking prefix set", bool(values.get("booking_prefix"))),
        ],
        "payment_setup_completed": [
            ("A payment gateway is enabled", bool(gateways)),
            ("Every enabled gateway passed its connection test", bool(gateways) and all(g.last_test_status == "connected" for g in gateways)),
            ("Every enabled gateway has its webhook secret configured", bool(gateways) and all(webhook_for.get(g.provider_name, False) for g in gateways)),
        ],
        "email_setup_completed": [
            ("SMTP configured", smtp_configured),
            ("At least one email delivered", email_delivered),
        ],
        "storage_setup_completed": [
            ("Cloudinary configured", bool((getattr(app_settings, "CLOUDINARY_URL", "") or "").strip())),
        ],
        "security_check_completed": [
            ("Platform JWT signing key is at least 32 characters", len((app_settings.JWT_SECRET_KEY or "").strip()) >= 32),
            ("Settings encryption key set", bool((getattr(app_settings, "SETTINGS_ENCRYPTION_KEY", "") or "").strip())),
            ("Redis configured when running more than one worker", workers <= 1 or bool((getattr(app_settings, "REDIS_URL", "") or "").strip())),
        ],
    }


def get_setup_progress(db: Session) -> dict:
    """Platform Setup checklist progress for the admin dashboard (e.g.
    "5/7 complete"). Each step is derived from real configuration checks
    (_setup_checks) -- gateways connected, webhooks set, SMTP delivering,
    signing key valid -- never from a manually toggled flag. The old
    *_completed AppSetting flags are still returned as `acknowledged` for
    reference but don't count towards completion."""
    flags = {
        s.key: str(s.value or "").lower() == "true"
        for s in db.query(AppSetting).filter(AppSetting.key.in_(SETUP_CHECKLIST_KEYS)).all()
    }
    checks = _setup_checks(db)
    steps = {key: all(ok for _label, ok in checks[key]) for key in SETUP_CHECKLIST_KEYS}
    completed = sum(1 for done in steps.values() if done)
    total = len(SETUP_CHECKLIST_KEYS)
    return {
        "steps": steps,
        "details": {
            key: {
                "done": steps[key],
                "acknowledged": flags.get(key, False),
                "checks": [{"label": label, "ok": ok} for label, ok in checks[key]],
            }
            for key in SETUP_CHECKLIST_KEYS
        },
        "completed": completed,
        "total": total,
        "percent": round((completed / total) * 100) if total else 0,
    }


def get_affiliate_setting(db: Session, key: str, default: str = "") -> str:
    """Single read-through accessor for affiliate.* settings so callers
    (commission engine, payout request flow, link creation) don't each
    re-implement the seed-then-query dance.

    Deliberately does NOT call seed_settings() (see get_commission_percentage
    for why): callers here run mid-transaction with uncommitted changes
    already staged on other objects (a conversion being adjusted, a payout
    being created), and seed_settings()'s unconditional db.commit() would
    flush + expire those objects out from under the caller.
    """
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    return setting.value if setting and setting.value is not None else default

DEFAULT_PAYMENT_SETTINGS = [
    {"provider_name": "stripe", "is_enabled": False, "public_key": "", "secret_key": "", "surcharge_percentage": "0", "mode": "test"},
    {"provider_name": "paypal", "is_enabled": False, "public_key": "", "secret_key": "", "surcharge_percentage": "0", "mode": "test"},
]

DEFAULT_API_SETTINGS = [
    {"api_name": "google_maps", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
    {"api_name": "email_service", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
    {"api_name": "sms_service", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
    {"api_name": "brightlane", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
    # api_key = Viator exp-api-key, api_secret = Viator affiliate Partner ID
    # (PID). Read at runtime by app/services/viator.py for the public
    # "External Day Trips" section.
    {"api_name": "viator", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
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


def get_commission_percentage(db: Session):
    """Admin-configured platform-minimum supplier commission percentage,
    used whenever a supplier has no commission_percentage of their own set
    - see the DEFAULT_SETTINGS entry above for what this drives.

    Deliberately does NOT call seed_settings() here (unlike get_settings()):
    this is a read used mid-transaction from booking/pricing calculations
    that may already have uncommitted changes staged on other objects in the
    same session - seed_settings()'s unconditional db.commit() would flush
    and expire those objects, silently turning in-memory floats back into
    Decimal on next access. The row is seeded elsewhere (GET /settings,
    /settings/public) long before this is ever the first caller in practice;
    the fallback below covers the case where it somehow isn't yet.
    """
    from decimal import Decimal, InvalidOperation

    setting = db.query(AppSetting).filter(AppSetting.key == "supplier_commission_percentage").first()
    try:
        return Decimal(str(setting.value)) if setting and setting.value not in (None, "") else Decimal("10")
    except (InvalidOperation, TypeError):
        return Decimal("10")


def get_default_admin_markup_percentage(db: Session):
    """Default percentage used for new admin-created pricing slabs."""
    return _get_percentage_setting(db, "default_admin_markup_percentage", "0")


def _get_percentage_setting(db: Session, key: str, default: str) -> "Decimal":
    from decimal import Decimal, InvalidOperation

    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    try:
        return Decimal(str(setting.value)) if setting and setting.value not in (None, "") else Decimal(default)
    except (InvalidOperation, TypeError):
        return Decimal(default)


def get_booking_prefix(db: Session) -> str:
    """Admin-configured booking-code prefix (AppSetting key "booking_prefix",
    default "TVA") -- see services.bookings._booking_code, which appends
    "C"/customer or "A"/agent plus the booking id (e.g. TVAC-1024)."""
    setting = db.query(AppSetting).filter(AppSetting.key == "booking_prefix").first()
    value = (setting.value if setting else None) or "TVA"
    return str(value).strip() or "TVA"


def get_agent_commission_max(db: Session):
    """Admin-configured MAXIMUM commission percentage Tourvaa will pay an
    agent (Agent.discount_type == "percentage"). Unlike supplier commission,
    this flows Tourvaa -> agent, so it is a ceiling enforced on every write
    of Agent.discount_value, not a floor an agent can self-raise - see
    services.agents.update_agent_discount."""
    return _get_percentage_setting(db, "agent_commission_max_percentage", "5")


def get_agent_default_commission(db: Session):
    """Admin-configured default commission % a new agent is shown on the
    post-login commission-consent popup (see CommissionConsentModal). Set
    onto Agent.discount_type/discount_value the moment the agent accepts -
    see services.agents.accept_agent_commission - since (unlike supplier's
    NULL-means-platform-minimum resolution) an agent's real payout fields
    don't otherwise resolve to any global setting."""
    return _get_percentage_setting(db, "agent_default_commission_percentage", "3")


def get_affiliate_default_commission(db: Session):
    """Admin-configured default commission % a new affiliate is shown on the
    post-login commission-consent popup (see CommissionConsentModal). Set
    onto Affiliate.commission_percentage the moment the affiliate accepts -
    see services.affiliates.accept_affiliate_commission - since an
    affiliate's real payout field otherwise stays at its column default (0),
    not any global setting."""
    return _get_percentage_setting(db, "affiliate_default_commission_value", "3")


def get_affiliate_commission_max(db: Session):
    """Admin-configured MAXIMUM commission percentage Tourvaa will pay an
    affiliate (Affiliate.commission_percentage and percentage-type
    AffiliateCommissionRule rows). Ceiling, not a floor - see
    services.affiliates and services.affiliate_commission_rules."""
    return _get_percentage_setting(db, "affiliate_commission_max_percentage", "5")


def _get_int_setting(db: Session, key: str, default: int) -> int:
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    try:
        return int(setting.value) if setting and setting.value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _get_bool_setting(db: Session, key: str, default: bool) -> bool:
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not setting or setting.value in (None, ""):
        return default
    return str(setting.value).strip().lower() in ("true", "1", "yes", "on")


def get_allow_agent_markup(db: Session) -> bool:
    """Whether an agent may set their own retail markup on top of the
    storefront price. Default OFF (commission-only agent model) -- see the
    allow_agent_markup DEFAULT_SETTINGS entry."""
    return _get_bool_setting(db, "allow_agent_markup", False)


def get_allow_agent_and_affiliate_same_booking(db: Session) -> bool:
    """Whether a single booking may pay commission to both an agent and an
    affiliate. Default OFF -- see services.bookings.supplier_accept_booking,
    which skips affiliate conversion recording for an agent-sourced booking
    unless this is enabled."""
    return _get_bool_setting(db, "allow_agent_and_affiliate_commission_same_booking", False)


def compute_commission_preview(db: Session, sample_price=None) -> dict:
    """Admin-facing "what does 120 actually split into" preview for the
    Pricing & Commission settings screen -- uses the SAME configured
    percentages real bookings would use (get_commission_percentage,
    get_agent_default_commission, get_affiliate_default_commission), not
    hardcoded example numbers, so the preview never drifts from reality."""
    from decimal import Decimal

    price = Decimal(str(sample_price)) if sample_price is not None else Decimal("120")
    commission_pct = get_commission_percentage(db)
    agent_pct = get_agent_default_commission(db)
    affiliate_pct = get_affiliate_default_commission(db)

    commission_amount = (price * commission_pct / Decimal("100")).quantize(Decimal("0.01"))
    supplier_net = price - commission_amount
    agent_amount = (price * agent_pct / Decimal("100")).quantize(Decimal("0.01"))
    affiliate_amount = (price * affiliate_pct / Decimal("100")).quantize(Decimal("0.01"))

    return {
        "sample_price": str(price),
        "tourvaa_commission_percentage": str(commission_pct),
        "direct": {
            "supplier": str(supplier_net),
            "tourvaa": str(commission_amount),
        },
        "agent": {
            "supplier": str(supplier_net),
            "agent_commission_percentage": str(agent_pct),
            "agent": str(agent_amount),
            "tourvaa": str(commission_amount - agent_amount),
        },
        "affiliate": {
            "supplier": str(supplier_net),
            "affiliate_commission_percentage": str(affiliate_pct),
            "affiliate": str(affiliate_amount),
            "tourvaa": str(commission_amount - affiliate_amount),
        },
    }


def get_security_status(db: Session) -> dict:
    """Read-only status for the unified JWT key and supporting services."""
    from app.config import settings as app_settings
    import os
    try:
        workers = int(os.environ.get("WEB_CONCURRENCY", "1") or "1")
    except ValueError:
        workers = 1
    jwt_secret = (app_settings.JWT_SECRET_KEY or "").strip()
    return {
        "jwt_secrets": {
            "platform": "configured (single signing key)" if len(jwt_secret) >= 32 else "missing or too short (minimum 32 characters)",
        },
        "redis": "configured" if str(getattr(app_settings, "REDIS_URL", "") or "").strip() else ("configured (not required for one worker)" if workers <= 1 else "missing (required for multiple workers)"),
        "cloudinary": "configured" if str(getattr(app_settings, "CLOUDINARY_URL", "") or "").strip() else "not configured",
        "settings_encryption_key": "configured" if str(getattr(app_settings, "SETTINGS_ENCRYPTION_KEY", "") or "").strip() else "missing",
    }


def get_default_deposit_percentage(db: Session):
    """Admin-configured platform-wide fallback deposit percentage, used only
    when a tour has no deposit_percentage/booking_deposit of its own set -
    see services.bookings._deposit_config and
    routers.payments_gateway._minimum_deposit_amount, the two places that
    resolve a tour's effective deposit terms."""
    return _get_percentage_setting(db, "default_deposit_percentage", "20")


def get_default_deposit_cutoff_days(db: Session) -> int:
    """Admin-configured fallback for how many days before departure a
    deposit is still offered, used only when the tour itself has no
    deposit_cutoff_days set. See get_default_deposit_percentage."""
    return _get_int_setting(db, "default_deposit_cutoff_days", 30)


def get_default_balance_payment_deadline_days(db: Session) -> int:
    """Admin-configured fallback for how many days before departure the
    remaining balance is due, used only when the tour itself has no
    balance_payment_deadline_days set. See get_default_deposit_percentage."""
    return _get_int_setting(db, "default_balance_payment_deadline_days", 14)


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


def test_payment_connection(
    db: Session,
    provider_name: str,
    actor: User | None = None,
    request=None,
) -> dict:
    """Makes a real, side-effect-free authenticated call to Stripe/PayPal with
    the currently configured credentials, so an admin can tell a saved key
    actually works instead of finding out the hard way at checkout time (the
    secret/client id+secret were previously stored and used blindly -- never
    health-checked anywhere in the codebase). Uses plain HTTP calls to match
    how app.services.payments_gateway already talks to both gateways (this
    codebase has no `stripe` SDK dependency installed).

    Persists the outcome on the PaymentSetting row (last_test_status/
    last_test_at/last_test_error) so the UI can display "last checked"
    without re-testing on every page load."""
    from datetime import datetime, timezone
    import base64
    import requests as http_requests
    from fastapi import HTTPException

    provider = (provider_name or "").strip().lower()
    if provider not in ("stripe", "paypal"):
        raise HTTPException(status_code=404, detail="Unknown payment provider")

    setting = (
        db.query(PaymentSetting)
        .filter(PaymentSetting.provider_name == provider)
        .first()
    )

    checked_at = datetime.now(timezone.utc)
    connected = False
    mode = None
    error = None

    if provider == "stripe":
        secret = decrypt_secret(setting.secret_key) if setting and setting.secret_key else ""
        if not secret:
            error = "Not configured"
        else:
            mode = "live" if secret.startswith(("sk_live_", "rk_live_")) else "test"
            try:
                resp = http_requests.get(
                    "https://api.stripe.com/v1/balance",
                    headers={"Authorization": f"Bearer {secret}"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    connected = True
                elif resp.status_code == 401:
                    error = "Authentication failed: invalid Stripe secret key"
                else:
                    body = resp.json() if resp.content else {}
                    error = body.get("error", {}).get("message") or f"Stripe returned HTTP {resp.status_code}"
            except Exception as exc:
                error = f"Could not reach Stripe: {exc}"
    else:  # paypal
        client_id = setting.public_key if setting else ""
        client_secret = decrypt_secret(setting.secret_key) if setting and setting.secret_key else ""
        if not client_id or not client_secret:
            error = "Not configured"
        else:
            provider_mode = (getattr(setting, "mode", "sandbox") or "sandbox")
            mode = "live" if provider_mode == "live" else "sandbox"
            base_url = "https://api-m.paypal.com" if mode == "live" else "https://api-m.sandbox.paypal.com"
            try:
                credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
                resp = http_requests.post(
                    f"{base_url}/v1/oauth2/token",
                    headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
                    data="grant_type=client_credentials",
                    timeout=10,
                )
                if resp.status_code == 200:
                    connected = True
                elif resp.status_code == 401:
                    error = "Authentication failed: invalid PayPal client id/secret"
                else:
                    body = resp.json() if resp.content else {}
                    error = body.get("error_description") or body.get("message") or f"PayPal returned HTTP {resp.status_code}"
            except Exception as exc:
                error = f"Could not reach PayPal: {exc}"

    result = {
        "provider": provider,
        "connected": connected,
        "mode": mode,
        "error": error,
        "checked_at": checked_at.isoformat(),
    }

    if setting:
        setting.last_test_status = "connected" if connected else "failed"
        setting.last_test_at = checked_at
        setting.last_test_error = error
        db.commit()
        db.refresh(setting)

    log_audit(
        db,
        actor=actor,
        action="test_payment_connection",
        entity_type="payment_setting",
        entity_id=setting.id if setting else None,
        new_values={"provider": provider, "connected": connected, "mode": mode, "error": error},
        request=request,
    )
    db.commit()

    return result


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


class SettingsValidationError(ValueError):
    """Raised when an incoming settings value would misrepresent behavior
    the code doesn't actually implement (see _validate_money_settings)."""


def _validate_money_settings(values: dict[str, str | None]) -> None:
    """money_decimal_places/money_rounding_method are documentation-only --
    app.utils.money.money() hardcodes Decimal("0.01")/ROUND_HALF_UP as a
    Python constant and does not read these settings at all (deliberately:
    money() is called extremely frequently across pricing/booking
    calculations with no db session in scope at most call sites, so making
    it DB-backed, even via a cached value, would add risk to code that must
    never have surprising rounding behavior for real money). Reject any
    value that doesn't match reality so an admin can never be misled into
    thinking a save changed actual rounding/precision."""
    if "money_decimal_places" in values and values["money_decimal_places"] not in (None, "2"):
        raise SettingsValidationError(
            "money_decimal_places is documentation-only and must be \"2\" -- "
            "app.utils.money.money() hardcodes 2 decimal places and does not "
            "read this setting."
        )
    if "money_rounding_method" in values and values["money_rounding_method"] not in (None, "HALF_UP"):
        raise SettingsValidationError(
            "money_rounding_method is documentation-only and must be \"HALF_UP\" -- "
            "app.utils.money.money() hardcodes ROUND_HALF_UP and does not read "
            "this setting."
        )


def _validate_timezone_setting(values: dict[str, str | None]) -> None:
    if "timezone" not in values:
        return
    timezone_name = normalize_timezone_name(values.get("timezone"))
    if not timezone_name:
        raise SettingsValidationError("Timezone is required")
    if timezone_name not in SUPPORTED_TIMEZONES:
        raise SettingsValidationError(f'Unsupported IANA timezone: "{timezone_name}"')


def _validate_admin_markup_setting(values: dict[str, str | None]) -> None:
    if "default_admin_markup_percentage" not in values:
        return
    from decimal import Decimal, InvalidOperation
    try:
        percentage = Decimal(str(values["default_admin_markup_percentage"]))
    except (InvalidOperation, TypeError):
        raise SettingsValidationError("Default admin markup must be a number between 0 and 100")
    if percentage < 0 or percentage > 100:
        raise SettingsValidationError("Default admin markup must be between 0 and 100 percent")


def update_settings(
    db: Session,
    values: dict[str, str | None],
    actor: User | None = None,
    request=None,
):
    values = dict(values)
    if "timezone" in values:
        values["timezone"] = normalize_timezone_name(values.get("timezone"))
    _validate_money_settings(values)
    _validate_timezone_setting(values)
    _validate_admin_markup_setting(values)
    seed_settings(db)
    # "currency" (booking group) and "default_currency" (general group) are
    # two historical keys for the same platform-wide default -- treat
    # "currency" (the one with an actual validated dropdown in the UI) as
    # authoritative and always mirror it onto "default_currency" so the two
    # can never drift apart again (they previously did, see migration
    # 20260720_0026). The whole settings form is submitted on every save, so
    # a stale "default_currency" would otherwise silently overwrite a fresh
    # "currency" change.
    if values.get("currency"):
        values["default_currency"] = values["currency"]
    elif values.get("default_currency"):
        values["currency"] = values["default_currency"]

    old_values = {
        setting.key: setting.value
        for setting in db.query(AppSetting).filter(AppSetting.key.in_(values.keys())).all()
    }

    for key, value in values.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()

        if setting:
            setting.value = value

    commission_effects = _enforce_commission_bounds(db, old_values, values)

    log_audit(
        db,
        actor=actor,
        action="update_settings",
        entity_type="settings",
        old_values=old_values,
        new_values=values,
        request=request,
    )
    if commission_effects:
        log_audit(
            db,
            actor=actor,
            action="enforce_commission_bounds",
            entity_type="settings",
            new_values=commission_effects,
            request=request,
        )
    db.commit()
    return get_settings(db)


def _notify_users(db: Session, user_ids: set[int], *, notification_type: str, title: str, message: str) -> None:
    from app.services.notifications import enqueue_notification
    for uid in user_ids:
        if uid:
            enqueue_notification(db, user_id=uid, notification_type=notification_type, title=title, message=message)


def _enforce_commission_bounds(db: Session, old_values: dict, new_values: dict) -> dict:
    """A commission minimum/maximum is meant to hold at all times, not just
    at the moment an individual supplier/agent/affiliate record is next
    written. When admin changes one of these three platform settings here,
    immediately bring every existing account back into compliance instead
    of only gating future writes (services.suppliers.update_supplier,
    services.agents.update_agent_discount, services.affiliates.update_affiliate,
    services.affiliate_commission_rules) - so the new bound reflects on
    every account (and every affiliate commission rule, which covers
    per-tour rates) immediately, in this one place, with no manual per-account
    editing required. Accounts with no rate of their own already live-resolve
    to this setting on every read (see get_commission_percentage /
    resolve_effective_commission_percentage) so they need no DB write at all
    to pick up the change - they are still notified below, since their
    effective rate changed even though nothing was written for them.

    Notifies every affected account's user, and returns a summary of what
    changed for the audit log.
    """
    from decimal import Decimal, InvalidOperation

    def _changed_decimal(key: str):
        if key not in new_values or new_values.get(key) == old_values.get(key):
            return None
        try:
            return Decimal(str(new_values[key]))
        except (InvalidOperation, TypeError):
            return None

    effects: dict = {}

    new_supplier_min = _changed_decimal("supplier_commission_percentage")
    if new_supplier_min is not None:
        from app.models.suppliers import Supplier
        affected = (
            db.query(Supplier)
            .filter(Supplier.commission_percentage.is_(None) | (Supplier.commission_percentage < new_supplier_min))
            .all()
        )
        user_ids = {s.user_id for s in affected}
        raised = (
            db.query(Supplier)
            .filter(Supplier.commission_percentage.isnot(None), Supplier.commission_percentage < new_supplier_min)
            .update({Supplier.commission_percentage: new_supplier_min}, synchronize_session=False)
        )
        if raised:
            effects["suppliers_raised_to_minimum"] = raised
        if user_ids:
            effects["suppliers_notified"] = len(user_ids)
            _notify_users(
                db, user_ids,
                notification_type="commission_rate_changed",
                title="Tourvaa commission rate updated",
                message=f"The Tourvaa commission rate on your bookings is now {new_supplier_min}%.",
            )

    new_agent_max = _changed_decimal("agent_commission_max_percentage")
    if new_agent_max is not None:
        from app.models.agents import Agent
        affected_agents = (
            db.query(Agent)
            .filter(Agent.discount_type == "percentage", Agent.discount_value > new_agent_max)
            .all()
        )
        user_ids = {a.user_id for a in affected_agents}
        capped = (
            db.query(Agent)
            .filter(Agent.discount_type == "percentage", Agent.discount_value > new_agent_max)
            .update({Agent.discount_value: new_agent_max}, synchronize_session=False)
        )
        if capped:
            effects["agents_capped_to_maximum"] = capped
        if user_ids:
            _notify_users(
                db, user_ids,
                notification_type="commission_rate_changed",
                title="Your commission rate has changed",
                message=f"Your approved commission rate has been capped to the new platform maximum of {new_agent_max}%.",
            )

    new_affiliate_max = _changed_decimal("affiliate_commission_max_percentage")
    if new_affiliate_max is not None:
        from app.models.affiliates import Affiliate
        from app.models.affiliate_tracking import AffiliateCommissionRule
        affected_affiliates = db.query(Affiliate).filter(Affiliate.commission_percentage > new_affiliate_max).all()
        user_ids = {a.user_id for a in affected_affiliates}
        capped_affiliates = (
            db.query(Affiliate)
            .filter(Affiliate.commission_percentage > new_affiliate_max)
            .update({Affiliate.commission_percentage: new_affiliate_max}, synchronize_session=False)
        )
        capped_rules = (
            db.query(AffiliateCommissionRule)
            .filter(AffiliateCommissionRule.commission_type == "percentage", AffiliateCommissionRule.percentage > new_affiliate_max)
            .update({AffiliateCommissionRule.percentage: new_affiliate_max}, synchronize_session=False)
        )
        if capped_affiliates:
            effects["affiliates_capped_to_maximum"] = capped_affiliates
        if capped_rules:
            effects["affiliate_rules_capped_to_maximum"] = capped_rules
        if user_ids:
            _notify_users(
                db, user_ids,
                notification_type="commission_rate_changed",
                title="Your commission rate has changed",
                message=f"Your commission rate has been capped to the new platform maximum of {new_affiliate_max}%.",
            )

    return effects


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
        "paypal_webhook_id": paypal.webhook_id if paypal else "",
        "payment_surcharge_percentage": surcharge,
        "default_payment_mode": stripe.mode if stripe else (paypal.mode if paypal else "test"),
        "stripe_last_test_status": stripe.last_test_status if stripe else None,
        "stripe_last_test_at": stripe.last_test_at if stripe else None,
        "stripe_last_test_error": stripe.last_test_error if stripe else None,
        "paypal_last_test_status": paypal.last_test_status if paypal else None,
        "paypal_last_test_at": paypal.last_test_at if paypal else None,
        "paypal_last_test_error": paypal.last_test_error if paypal else None,
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
    if values.get("paypal_webhook_id") is not None:
        paypal_values["webhook_id"] = values["paypal_webhook_id"]

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
    viator = rows.get("viator")

    gm_key = decrypt_secret(google_maps.api_key if google_maps else "")
    em_key = decrypt_secret(email_service.api_key if email_service else "")
    sms_key = decrypt_secret(sms_service.api_key if sms_service else "")
    viator_key = decrypt_secret(viator.api_key if viator else "")
    # The Partner ID isn't a secret (it shows up in outbound URLs), so unlike
    # api_key above it's returned in full rather than masked - the admin
    # needs to be able to read it back to verify it, not just confirm it's set.
    viator_pid = decrypt_secret(viator.api_secret if viator else "")
    return {
        "google_map_api_key": mask_secret(gm_key),
        "google_maps_api_placeholder": mask_secret(gm_key),
        "email_api_key": mask_secret(em_key),
        "email_api_placeholder": mask_secret(em_key),
        "sms_api_key": mask_secret(sms_key),
        "sms_api_placeholder": mask_secret(sms_key),
        "brightlane_external_link": brightlane.api_url if brightlane else "",
        "brightlane_external_link_placeholder": brightlane.api_url if brightlane else "",
        "viator_api_key": mask_secret(viator_key),
        "viator_api_key_placeholder": mask_secret(viator_key),
        "viator_affiliate_pid": viator_pid,
        "viator_enabled": bool(viator.is_enabled) if viator else False,
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
        "viator_api_key": ("viator", "api_key"),
        "viator_api_key_placeholder": ("viator", "api_key"),
        "viator_affiliate_pid": ("viator", "api_secret"),
        "viator_enabled": ("viator", "is_enabled"),
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


def get_or_create_smtp_settings(db: Session) -> SmtpSetting:
    setting = db.query(SmtpSetting).first()
    if not setting:
        setting = SmtpSetting()
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def get_smtp_settings_payload(db: Session):
    setting = get_or_create_smtp_settings(db)
    password = decrypt_secret(setting.password or "")
    return {
        "is_enabled": setting.is_enabled,
        "host": setting.host or "",
        "port": setting.port,
        "username": setting.username or "",
        "password": mask_secret(password),
        "password_placeholder": mask_secret(password),
        "from_name": setting.from_name,
        "from_email": setting.from_email or "",
        "reply_to": setting.reply_to or "",
        "use_ssl": setting.use_ssl,
        "use_starttls": setting.use_starttls,
        "timeout_seconds": setting.timeout_seconds,
    }


_SMTP_FIELD_MAP = {
    "is_enabled": "is_enabled",
    "host": "host",
    "port": "port",
    "username": "username",
    "password": "password",
    "password_placeholder": "password",
    "from_name": "from_name",
    "from_email": "from_email",
    "reply_to": "reply_to",
    "use_ssl": "use_ssl",
    "use_starttls": "use_starttls",
    "timeout_seconds": "timeout_seconds",
}


def update_smtp_settings_payload(
    db: Session,
    values: dict[str, str | bool | int | None],
    actor: User | None = None,
    request=None,
):
    setting = get_or_create_smtp_settings(db)

    old_values = {column: getattr(setting, column) for column in set(_SMTP_FIELD_MAP.values())}

    for incoming_key, column in _SMTP_FIELD_MAP.items():
        if incoming_key not in values or values[incoming_key] is None:
            continue
        value = values[incoming_key]
        if column in _SMTP_SECRET_FIELDS:
            # Blank/omitted password means "keep the existing value" -- the
            # masked placeholder returned by GET is never round-tripped back
            # in as the real secret (same contract as payment/api settings).
            if isinstance(value, str) and value.strip():
                setattr(setting, column, encrypt_secret(value.strip()))
            continue
        setattr(setting, column, value.strip() if isinstance(value, str) else value)

    safe_old_values = {
        k: (mask_secret(decrypt_secret(v or "")) if k in _SMTP_SECRET_FIELDS else v)
        for k, v in old_values.items()
    }
    safe_new_values = {
        k: (mask_secret(v) if k in _SMTP_SECRET_FIELDS and isinstance(v, str) else v)
        for k, v in values.items()
    }
    log_audit(
        db,
        actor=actor,
        action="update_smtp_settings",
        entity_type="smtp_setting",
        entity_id=setting.id,
        old_values=safe_old_values,
        new_values=safe_new_values,
        request=request,
    )
    db.commit()
    db.refresh(setting)
    return get_smtp_settings_payload(db)


def send_smtp_test_email(db: Session, to_email: str, actor: User | None = None, request=None) -> dict:
    """Sends a test email using whatever SMTP config is currently effective
    (services.settings mirrors app.utils.mailer._effective_smtp_config's own
    resolution: the saved SmtpSetting row when enabled+host is set, otherwise
    the env-var fallback) -- same "save first, then test" flow already used
    by services.email_templates.send_test_email, so there's one testable
    notion of "what would actually be used right now" rather than a second,
    divergent draft-config code path."""
    from fastapi import HTTPException
    from app.utils.mailer import send_email

    setting = get_or_create_smtp_settings(db)
    used_custom_smtp = bool(setting.is_enabled and setting.host)
    subject = "Tourvaa SMTP test email"
    html = (
        "<p>This is a test email from Tourvaa's Email / SMTP settings.</p>"
        f"<p>Sent using {'your saved custom SMTP configuration' if used_custom_smtp else 'the platform default (environment) mail server, since custom SMTP is disabled or missing a host)'}.</p>"
        "<p>If you received this, outbound email delivery is working.</p>"
    )
    try:
        result = send_email(to_email, subject, html, template_key="smtp:test")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Could not send test email: {error}")

    log_audit(db, actor=actor, action="test_smtp_settings", entity_type="smtp_setting", entity_id=setting.id, new_values={"to_email": to_email, "used_custom_smtp": used_custom_smtp}, request=request)
    db.commit()

    return {"sent": True, "to": to_email, "message_id": result.message_id, "used_custom_smtp": used_custom_smtp}
