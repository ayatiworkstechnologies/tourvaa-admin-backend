from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

from app.database import SessionLocal, engine
from app.config import get_storage_root, settings

from app.modules.roles.models import Role
from app.modules.admin_modules.models import AdminModule
from app.modules.permissions.models import Permission, RolePermission
from app.modules.users.models import User
from app.modules.settings.models import ApiSetting, AppSetting, PaymentSetting
from app.modules.email_templates.models import EmailTemplate
from app.modules.audit.models import AuditLog
from app.modules.customers.models import Customer, CustomerCommunication, CustomerSavedTraveller, CustomerCancellationRequest
from app.modules.cms.models import Country, State, City, TourCategory, TourSubcategory, TourSubcategoryMap, Tour
from app.modules.bookings.models import Booking, BookingTraveller, BookingOptionalActivity, BookingAccommodation, BookingExtension, BookingStatusHistory, BookingCommunication, MessageReply, EmailLog
from app.modules.payments.models import Payment, PaymentTransaction, PaymentHold
from app.modules.tours.models import (
    TourOverview, TourItinerary, TourInclusion, TourExclusion, TourHighlight,
    TourSimilar, TourExtension, TourGalleryImage,
    TourPricing, TourOptionalActivity, TourAccommodationExtra,
    TourCalendar, TourUnavailableDate, TourDiscount,
)
from app.modules.suppliers.models import Supplier, SupplierContact, SupplierBusinessInfo, SupplierVehicle, SupplierInvoicing, SupplierDocument
from app.modules.agents.models import Agent, AgentContact, AgentBusinessInfo, AgentInvoicing, AgentDocument
from app.modules.affiliates.models import Affiliate, AffiliateMarketingInfo, AffiliateInvoicing, AffiliateDocument
from app.seed import seed_default_roles_and_permissions
from app.modules.email_templates.service import seed_email_templates

from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router
from app.modules.roles.router import router as roles_router
from app.modules.permissions.router import router as permissions_router
from app.modules.admin_modules.router import router as admin_modules_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.profile.router import router as profile_router
from app.modules.settings.router import router as settings_router
from app.modules.email_templates.router import router as email_templates_router
from app.modules.uploads.router import router as uploads_router
from app.modules.client.router import router as client_router
from app.modules.customers.router import router as customers_router
from app.modules.customers.customer_router import router as customer_portal_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.agents.router import router as agents_router
from app.modules.affiliates.router import router as affiliates_router
from app.modules.cms.router import router as cms_router
from app.modules.cms.geo_seed_router import router as geo_seed_router
from app.modules.cms.geo_router import router as geo_router
from app.modules.bookings.router import router as bookings_router, supplier_router as bookings_supplier_router, supplier_portal_router as bookings_supplier_portal_router, agent_portal_router as bookings_agent_portal_router
from app.modules.payments.router import router as payments_router
from app.modules.tours.router import discounts_router, router as tour_detail_router
from app.modules.invoices.models import Invoice, InvoiceItem
from app.modules.notifications.models import Notification, NotificationLog
from app.modules.sessions.models import UserSession, LoginHistory
from app.modules.invoices.router import router as invoices_router
from app.modules.notifications.router import router as notifications_router
from app.modules.reports.router import router as reports_router
from app.modules.sessions.router import router as sessions_router
from app.modules.audit.router import router as activity_logs_router, alias_router as audit_logs_alias_router
from app.modules.chatbot.models import ChatFAQ, ChatSession, ChatMessage
from app.modules.chatbot.router import router as chatbot_router
from app.modules.public.router import router as public_router

# New modules
from app.modules.tour_versions.models import TourVersion
from app.modules.tour_versions.router import router as tour_versions_router
from app.modules.payments.gateway_router import router as payments_gateway_router
from app.modules.supplier_ledger.models import SupplierLedger, SupplierPayout, SupplierPayoutItem
from app.modules.supplier_ledger.router import router as supplier_ledger_router
from app.modules.checkout.models import CheckoutSession
from app.modules.checkout.router import router as checkout_router
from app.modules.website_cms.models import (
    HomepageBanner, PopularDestination, PopularTour, TourOnDeal,
    Blog, CustomerReview, HelpCentreArticle, CmsPolicy,
    PromotionalPopup, ExternalLink, SitemapEntry,
)
from app.modules.website_cms.router import router as website_cms_router
from app.modules.cancellations.models import CancellationRequest, RefundRule
from app.modules.cancellations.router import router as cancellations_router
from app.modules.booking_calendar.models import BookingCalendarEvent
from app.modules.booking_calendar.router import router as booking_calendar_router
from app.modules.affiliate_tracking.models import AffiliateLink, AffiliateClick, AffiliateConversion, AffiliatePayout
from app.modules.affiliate_tracking.router import router as affiliate_tracking_router
from app.modules.private_documents.router import router as private_documents_router

logger = logging.getLogger(__name__)


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
    }

    if not required_tables.issubset(tables):
        return False

    required_columns = {
        "roles": {"is_system"},
        "permissions": {"action", "is_system"},
        "customers": {"phone_country_code", "date_of_birth", "gender", "email_verified", "phone_verified"},
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
        },
    }

    for table_name, column_names in required_columns.items():
        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        if not column_names.issubset(existing_columns):
            return False

    return True


app = FastAPI(
    title="Tourvaa Backend",
    version="1.0.0"
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail or "An error occurred"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first = errors[0] if errors else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) if first.get("loc") else "unknown"
    message = f"{field}: {first.get('msg', 'Validation error')}" if field and field != "unknown" else first.get("msg", "Validation error")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"status": "error", "message": message, "detail": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "message": "An unexpected error occurred. Please try again later."},
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

_cors_origins = settings.cors_origins
_allow_credentials = _cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Client-Type", "X-Client-Version", "X-Device-Id"],
)

storage_root = get_storage_root()
storage_root.joinpath("uploads", "profile-images").mkdir(parents=True, exist_ok=True)
storage_root.joinpath("uploads", "admin-assets").mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_root)), name="storage")

# Private document storage — lives outside the public /storage mount
private_docs_root = storage_root.parent / "private-docs"
private_docs_root.joinpath("supplier-documents").mkdir(parents=True, exist_ok=True)
private_docs_root.joinpath("agent-documents").mkdir(parents=True, exist_ok=True)

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(roles_router, prefix="/api")
app.include_router(roles_router, prefix="/api/admin")
app.include_router(permissions_router, prefix="/api")
app.include_router(permissions_router, prefix="/api/admin")
app.include_router(admin_modules_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(profile_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(email_templates_router, prefix="/api")
app.include_router(uploads_router, prefix="/api")
app.include_router(client_router, prefix="/api")
app.include_router(customers_router, prefix="/api")
app.include_router(customer_portal_router, prefix="/api")
app.include_router(suppliers_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(affiliates_router, prefix="/api")
app.include_router(tour_detail_router, prefix="/api")
app.include_router(discounts_router, prefix="/api")
app.include_router(cms_router, prefix="/api")
app.include_router(geo_seed_router, prefix="/api")
app.include_router(geo_router, prefix="/api")
app.include_router(bookings_router, prefix="/api")
app.include_router(payments_router, prefix="/api")
app.include_router(invoices_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(activity_logs_router, prefix="/api")
app.include_router(audit_logs_alias_router, prefix="/api")
app.include_router(bookings_supplier_router, prefix="/api")
app.include_router(bookings_supplier_portal_router, prefix="/api")
app.include_router(bookings_agent_portal_router, prefix="/api")
app.include_router(chatbot_router, prefix="/api")
app.include_router(public_router, prefix="/api/public")

# New module routers
app.include_router(tour_versions_router, prefix="/api")
app.include_router(payments_gateway_router, prefix="/api")
app.include_router(supplier_ledger_router, prefix="/api")
app.include_router(checkout_router, prefix="/api")
app.include_router(website_cms_router, prefix="/api")
app.include_router(cancellations_router, prefix="/api")
app.include_router(booking_calendar_router, prefix="/api")
app.include_router(affiliate_tracking_router, prefix="/api")
app.include_router(private_documents_router, prefix="/api")

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







