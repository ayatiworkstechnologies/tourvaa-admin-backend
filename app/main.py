import asyncio
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
import logging

from app.database import SessionLocal, engine
from app.config import get_storage_root, settings
from app.middleware.cors import setup_cors
from app.middleware.csrf import CsrfMiddleware
from app.middleware.error_handlers import register_error_handlers

from app.models.roles import Role
from app.models.admin_modules import AdminModule
from app.models.permissions import Permission, RolePermission
from app.models.users import User
from app.models.settings import ApiSetting, AppSetting, PaymentSetting
from app.models.email_templates import EmailTemplate
from app.models.audit import AuditLog
from app.models.customers import Customer, CustomerCommunication, CustomerSavedTraveller, CustomerCancellationRequest, CustomerWishlistItem
from app.models.cms import Country, State, City, TourCategory, TourSubcategory, TourSubcategoryMap, Tour
from app.models.bookings import Booking, BookingTraveller, BookingOptionalActivity, BookingAccommodation, BookingExtension, BookingStatusHistory, BookingCommunication, MessageReply, EmailLog
from app.models.payments import Payment, PaymentTransaction, PaymentHold
from app.models.tours import (
    TourOverview, TourItinerary, TourInclusion, TourExclusion, TourHighlight,
    TourSimilar, TourExtension, TourGalleryImage,
    TourPricing, TourOptionalActivity, TourAccommodationExtra,
    TourCalendar, TourUnavailableDate, TourDiscount,
)
from app.models.suppliers import Supplier, SupplierApprovalHistory, SupplierContact, SupplierBusinessInfo, SupplierVehicle, SupplierInvoicing, SupplierDocument
from app.models.agents import Agent, AgentContact, AgentBusinessInfo, AgentInvoicing, AgentDocument
from app.models.affiliates import Affiliate, AffiliateMarketingInfo, AffiliateInvoicing, AffiliateDocument
from app.seed import seed_default_roles_and_permissions
from app.services.email_templates import seed_email_templates

from app.api.router import register_api_routes
from app.models.invoices import Invoice, InvoiceItem
from app.models.notifications import Notification, NotificationLog
from app.models.sessions import UserSession, LoginHistory
from app.models.chatbot import ChatFAQ, ChatSession, ChatMessage

# New modules
from app.models.tour_versions import TourVersion, TourReviewComment
from app.models.supplier_ledger import SupplierLedger, SupplierPayout, SupplierPayoutItem
from app.models.checkout import CheckoutSession
from app.models.website_cms import (
    HomepageBanner, PopularDestination, PopularTour, TourOnDeal,
    Blog, CustomerReview, HelpCentreArticle, CmsPolicy,
    PromotionalPopup, ExternalLink, SitemapEntry,
)
from app.models.cancellations import CancellationRequest, RefundRule
from app.models.reviews import TourReview
from app.models.booking_calendar import BookingCalendarEvent
from app.models.affiliate_tracking import (
    AffiliateLink,
    AffiliateClick,
    AffiliateAttribution,
    AffiliateCommissionRule,
    AffiliateConversion,
    AffiliatePayoutMethod,
    AffiliatePayout,
    AffiliatePayoutItem,
    AffiliateWalletTransaction,
)

logger = logging.getLogger(__name__)


def validate_production_config() -> None:
    """Refuse to start with unsafe settings when APP_ENV=production.

    APP_ENV defaults to "production" (see app/config/__init__.py) so any
    deployment that forgets to set it explicitly gets these checks too -
    that's the point, not an oversight.
    """
    if settings.APP_ENV != "production":
        return

    errors: list[str] = []

    if settings.APP_DEBUG:
        errors.append("APP_DEBUG must be false in production")

    # ALLOWED_ORIGINS=="*" in production is already refused at Settings()
    # construction time (see config/_require_explicit_cors_in_production),
    # before this function can even run.

    if settings.SUPER_ADMIN_PASSWORD == "Admin@123":
        errors.append("SUPER_ADMIN_PASSWORD must be changed from its default value in production")

    if len(settings.JWT_SECRET_KEY) < 32:
        errors.append("JWT_SECRET_KEY must be at least 32 characters in production")

    portal_secrets = {
        "SUPPLIER_JWT_SECRET_KEY": settings.SUPPLIER_JWT_SECRET_KEY,
        "AGENT_JWT_SECRET_KEY": settings.AGENT_JWT_SECRET_KEY,
        "CUSTOMER_JWT_SECRET_KEY": settings.CUSTOMER_JWT_SECRET_KEY,
        "ADMIN_JWT_SECRET_KEY": settings.ADMIN_JWT_SECRET_KEY,
    }
    unset_portal_secrets = [name for name, value in portal_secrets.items() if not value]
    if unset_portal_secrets:
        errors.append(
            f"{', '.join(unset_portal_secrets)} must be set to distinct values in production "
            "(each currently falls back to the shared JWT_SECRET_KEY)"
        )
    elif len(set(portal_secrets.values())) < len(portal_secrets):
        errors.append("SUPPLIER_JWT_SECRET_KEY, AGENT_JWT_SECRET_KEY, CUSTOMER_JWT_SECRET_KEY and ADMIN_JWT_SECRET_KEY must all be distinct in production")

    if not settings.STRIPE_WEBHOOK_SECRET:
        errors.append("STRIPE_WEBHOOK_SECRET must be set in production (Stripe webhooks are otherwise rejected at runtime)")

    if not settings.PAYPAL_WEBHOOK_ID:
        errors.append("PAYPAL_WEBHOOK_ID must be set in production (PayPal webhooks are otherwise rejected at runtime)")

    if errors:
        raise RuntimeError(
            "Refusing to start with unsafe production configuration:\n- " + "\n- ".join(errors)
        )


def validate_worker_concurrency() -> None:
    """Refuse to start with more than one worker process unless Redis is
    configured to back the state that would otherwise be process-local.

    Scheduled sweeps (`start_background_jobs`, below) take a Redis-backed
    per-tick lock (`app/utils/distributed_lock.py`) so only one worker runs
    each sweep per interval, and the /ws/messages ticket store + socket
    registry (`app/services/messaging_ws.py`) fall back to Redis-backed
    tickets plus a Redis pub/sub relay so a message reaches a user's socket
    regardless of which worker holds it. Both degrade to their original
    process-local behavior when REDIS_URL is unset, which is only safe for
    WEB_CONCURRENCY=1 - hence this still requires Redis for anything more.
    """
    workers = int(os.environ.get("WEB_CONCURRENCY", "1") or "1")
    if workers > 1 and not settings.REDIS_URL:
        raise RuntimeError(
            f"WEB_CONCURRENCY={workers} requires REDIS_URL to be set: background job "
            "sweeps and /ws/messages state fall back to process-local behavior without "
            "Redis, which is only correct for a single worker/instance. Set REDIS_URL "
            "to a shared Redis instance, or set WEB_CONCURRENCY=1."
        )


validate_worker_concurrency()
validate_production_config()


def schema_is_ready():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required_tables = {
        "roles",
        "permissions",
        "role_permissions",
        "users",
        "email_templates",
        "app_settings",
        "payment_settings",
        "api_settings",
        "audit_logs",
        "admin_modules",
        "user_roles",
        "customers",
        "customer_communications",
        "customer_saved_travellers",
        "customer_cancellation_requests",
        "customer_wishlist_items",
        "countries",
        "cities",
        "tour_categories",
        "tour_subcategories",
        "tour_subcategory_map",
        "tours",
        "suppliers",
        "supplier_contacts",
        "supplier_business_info",
        "supplier_vehicles",
        "supplier_invoicing",
        "supplier_documents",
        "supplier_approval_history",
        "agents",
        "agent_contacts",
        "agent_business_info",
        "agent_invoicing",
        "agent_documents",
        "affiliates",
        "affiliate_marketing_info",
        "affiliate_invoicing",
        "affiliate_documents",
        "bookings",
        "payments",
        "booking_travellers",
        "booking_optional_activities",
        "booking_accommodations",
        "booking_extensions",
        "booking_status_history",
        "booking_communications",
        "payment_transactions",
        "payment_holds",
        "invoices",
        "invoice_items",
        "notifications",
        "user_sessions",
        "message_replies",
        "email_logs",
        "notification_logs",
        "login_history",
        "chat_faqs",
        "chat_sessions",
        "chat_messages",
        "states",
        "tour_versions",
        "tour_review_comments",
        "supplier_ledgers",
        "supplier_payouts",
        "supplier_payout_items",
        "checkout_sessions",
        "cms_homepage_banners",
        "cms_popular_destinations",
        "cms_popular_tours",
        "cms_tours_on_deals",
        "cms_blogs",
        "cms_customer_reviews",
        "cms_help_centre",
        "cms_policies",
        "cms_promotional_popups",
        "cms_external_links",
        "cms_sitemap_entries",
        "cancellation_requests",
        "refund_rules",
        "tour_reviews",
        "booking_calendar_events",
        "affiliate_links",
        "affiliate_clicks",
        "affiliate_conversions",
        "affiliate_payouts",
        "affiliate_attributions",
        "affiliate_commission_rules",
        "affiliate_payout_methods",
        "affiliate_payout_items",
        "affiliate_wallet_transactions",
        "user_status_history",
    }

    if not required_tables.issubset(tables):
        return False

    required_columns = {
        "roles": {"is_system"},
        "permissions": {"action", "is_system"},
        "customers": {"phone_country_code", "date_of_birth", "gender", "email_verified", "phone_verified"},
        "supplier_payouts": {"paid_by"},
        "supplier_vehicles": {"vehicle_type", "registration_number"},
        "affiliate_links": {"link_type", "custom_alias", "status", "attribution_window_days"},
        "affiliate_conversions": {"commission_rule_id", "eligible_amount", "final_commission"},
        "affiliate_payouts": {"payout_method_id", "requested_at", "rejection_reason"},
        "bookings": {"affiliate_attribution_id"},
        "users": {
            "approval_status",
            "reset_password_token",
            "reset_password_expires_at",
            "token_version",
            "email_verified_at",
            "email_verification_token",
            "email_verification_expires_at",
            "two_factor_enabled",
            "force_password_reset",
            "user_type",
            "country_code",
            "mobile_number",
            "email_verified",
            "password_created_at",
            "account_status",
            "admin_verified",
            "admin_verified_at",
            "admin_verified_by",
            "deactivated_at",
            "deactivated_by",
            "deactivation_reason",
            "last_login_at",
            "updated_at",
            "failed_login_attempts",
            "locked_until",
        },
    }

    for table_name, column_names in required_columns.items():
        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        if not column_names.issubset(existing_columns):
            return False

    return True


# The interactive docs (/docs, /redoc) and the raw schema (/openapi.json)
# are disabled in production - they're a public, unauthenticated map of
# every route/model in the API, and were being hit repeatedly with no
# legitimate frontend caller (the admin/portal UIs never fetch this schema
# at runtime; only a human or a scanner browsing /docs would). Still fully
# available in non-production for local development and API exploration.
_docs_enabled = settings.APP_ENV != "production"

app = FastAPI(
    title="Tourvaa Backend",
    version="1.0.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)


register_error_handlers(app)


@app.on_event("startup")
def warn_if_chatbot_llm_unconfigured():
    from app.config import settings

    if not settings.ANTHROPIC_API_KEY:
        logger.warning(
            "ANTHROPIC_API_KEY is not set; the chatbot will run in keyword-only fallback mode "
            "(no LLM, no streaming). Set ANTHROPIC_API_KEY to enable full AI responses."
        )


@app.on_event("startup")
def run_seed():
    if schema_is_ready():
        db = SessionLocal()
        try:
            seed_default_roles_and_permissions(db)
            seed_email_templates(db)
        finally:
            db.close()
    else:
        logger.warning(
            "Database schema is not ready; skipping seed. Run `python -m alembic upgrade head` before starting the API."
        )

# How often to sweep for, and how long to wait before expiring, unpaid
# bookings that would otherwise hold their TourCalendar seats forever.
BOOKING_EXPIRY_SWEEP_INTERVAL_SECONDS = 15 * 60
BOOKING_EXPIRY_HOLD_MINUTES = 60


async def _expire_stale_bookings_loop():
    from app.services.bookings import expire_stale_pending_bookings
    from app.utils.distributed_lock import acquire_sweep_lock

    while True:
        await asyncio.sleep(BOOKING_EXPIRY_SWEEP_INTERVAL_SECONDS)
        try:
            if not await asyncio.to_thread(acquire_sweep_lock, "expire_stale_bookings", BOOKING_EXPIRY_SWEEP_INTERVAL_SECONDS - 60):
                continue
            db = SessionLocal()
            try:
                # Run the blocking DB work off the event loop thread.
                await asyncio.to_thread(expire_stale_pending_bookings, db, BOOKING_EXPIRY_HOLD_MINUTES)
            finally:
                db.close()
        except Exception:
            logger.exception("Stale booking expiry sweep failed")


# Cadences are daily/weekly/monthly at the coarsest, so a check every hour
# is frequent enough to catch a due schedule promptly without polling hard.
REPORT_SCHEDULE_SWEEP_INTERVAL_SECONDS = 60 * 60


async def _report_schedule_loop():
    from app.services.reports import run_due_report_schedules
    from app.utils.distributed_lock import acquire_sweep_lock

    while True:
        await asyncio.sleep(REPORT_SCHEDULE_SWEEP_INTERVAL_SECONDS)
        try:
            if not await asyncio.to_thread(acquire_sweep_lock, "report_schedule", REPORT_SCHEDULE_SWEEP_INTERVAL_SECONDS - 60):
                continue
            db = SessionLocal()
            try:
                await asyncio.to_thread(run_due_report_schedules, db)
            finally:
                db.close()
        except Exception:
            logger.exception("Report schedule sweep failed")


# Balance-due reminders only need to change once a day (stage boundaries are
# whole days), so an hourly check is plenty responsive without extra load.
BALANCE_DUE_REMINDER_SWEEP_INTERVAL_SECONDS = 60 * 60


async def _balance_due_reminder_loop():
    from app.services.invoices import check_balance_due_reminders
    from app.utils.distributed_lock import acquire_sweep_lock

    while True:
        await asyncio.sleep(BALANCE_DUE_REMINDER_SWEEP_INTERVAL_SECONDS)
        try:
            if not await asyncio.to_thread(acquire_sweep_lock, "balance_due_reminder", BALANCE_DUE_REMINDER_SWEEP_INTERVAL_SECONDS - 60):
                continue
            db = SessionLocal()
            try:
                await asyncio.to_thread(check_balance_due_reminders, db)
            finally:
                db.close()
        except Exception:
            logger.exception("Balance-due reminder sweep failed")


# Tour end-date reminders only need to change once a day (the 30-day/resend
# windows are whole-day boundaries), so an hourly check is plenty responsive.
TOUR_AVAILABILITY_REMINDER_SWEEP_INTERVAL_SECONDS = 60 * 60


async def _tour_availability_reminder_loop():
    from app.services.tour_availability import check_availability_end_date_reminders
    from app.utils.distributed_lock import acquire_sweep_lock

    while True:
        await asyncio.sleep(TOUR_AVAILABILITY_REMINDER_SWEEP_INTERVAL_SECONDS)
        try:
            if not await asyncio.to_thread(acquire_sweep_lock, "tour_availability_reminder", TOUR_AVAILABILITY_REMINDER_SWEEP_INTERVAL_SECONDS - 60):
                continue
            db = SessionLocal()
            try:
                await asyncio.to_thread(check_availability_end_date_reminders, db)
            finally:
                db.close()
        except Exception:
            logger.exception("Tour availability end-date reminder sweep failed")


# Each wishlist item's own weekly cadence is tracked per-row
# (last_reminder_sent_at) - a daily sweep is frequent enough to catch every
# item within a day of its 7-day mark without checking hourly.
WISHLIST_REMINDER_SWEEP_INTERVAL_SECONDS = 24 * 60 * 60


async def _wishlist_reminder_loop():
    from app.services.wishlist_reminders import check_wishlist_reminders
    from app.utils.distributed_lock import acquire_sweep_lock

    while True:
        await asyncio.sleep(WISHLIST_REMINDER_SWEEP_INTERVAL_SECONDS)
        try:
            if not await asyncio.to_thread(acquire_sweep_lock, "wishlist_reminder", WISHLIST_REMINDER_SWEEP_INTERVAL_SECONDS - 300):
                continue
            db = SessionLocal()
            try:
                await asyncio.to_thread(check_wishlist_reminders, db)
            finally:
                db.close()
        except Exception:
            logger.exception("Wishlist reminder sweep failed")


@app.on_event("startup")
async def start_background_jobs():
    if schema_is_ready():
        asyncio.create_task(_expire_stale_bookings_loop())
        asyncio.create_task(_report_schedule_loop())
        asyncio.create_task(_balance_due_reminder_loop())
        asyncio.create_task(_tour_availability_reminder_loop())
        asyncio.create_task(_wishlist_reminder_loop())

    from app.services.messaging_ws import start_redis_subscriber
    asyncio.create_task(start_redis_subscriber())

setup_cors(app)
app.add_middleware(CsrfMiddleware)

storage_root = get_storage_root()
storage_root.joinpath("uploads", "profile-images").mkdir(parents=True, exist_ok=True)
storage_root.joinpath("uploads", "admin-assets").mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_root)), name="storage")

# Private document storage -- lives outside the public /storage mount
private_docs_root = storage_root.parent / "private-docs"
private_docs_root.joinpath("supplier-documents").mkdir(parents=True, exist_ok=True)
private_docs_root.joinpath("agent-documents").mkdir(parents=True, exist_ok=True)
private_docs_root.joinpath("invoices").mkdir(parents=True, exist_ok=True)
private_docs_root.joinpath("itineraries").mkdir(parents=True, exist_ok=True)

register_api_routes(app)

from app.routers.affiliate_redirect import router as affiliate_redirect_router
app.include_router(affiliate_redirect_router)

@app.get("/")
def home():
    return {
        "status": "success",
        "message": "Tourvaa Backend Running"
    }


@app.get("/api/health")
def health():
    return {
        "status": "success",
        "message": "API working fine"
    }







