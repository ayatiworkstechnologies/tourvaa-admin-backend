from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
import logging

from app.database import SessionLocal, engine
from app.config import get_storage_root, settings
from app.middleware.cors import setup_cors
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
from app.models.tour_versions import TourVersion
from app.models.supplier_ledger import SupplierLedger, SupplierPayout, SupplierPayoutItem
from app.models.checkout import CheckoutSession
from app.models.website_cms import (
    HomepageBanner, PopularDestination, PopularTour, TourOnDeal,
    Blog, CustomerReview, HelpCentreArticle, CmsPolicy,
    PromotionalPopup, ExternalLink, SitemapEntry,
)
from app.models.cancellations import CancellationRequest, RefundRule
from app.models.booking_calendar import BookingCalendarEvent
from app.models.affiliate_tracking import AffiliateLink, AffiliateClick, AffiliateConversion, AffiliatePayout

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
        "booking_calendar_events",
        "affiliate_links",
        "affiliate_clicks",
        "affiliate_conversions",
        "affiliate_payouts",
        "user_status_history",
    }

    if not required_tables.issubset(tables):
        return False

    required_columns = {
        "roles": {"is_system"},
        "permissions": {"action", "is_system"},
        "customers": {"phone_country_code", "date_of_birth", "gender", "email_verified", "phone_verified"},
        "suppliers": {"commission_request_type", "commission_request_value", "commission_request_status", "commission_requested_at", "commission_reviewed_at"},
        "supplier_payouts": {"paid_by"},
        "supplier_vehicles": {"vehicle_type", "registration_number"},
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


register_error_handlers(app)


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

setup_cors(app)

storage_root = get_storage_root()
storage_root.joinpath("uploads", "profile-images").mkdir(parents=True, exist_ok=True)
storage_root.joinpath("uploads", "admin-assets").mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_root)), name="storage")

# Private document storage -- lives outside the public /storage mount
private_docs_root = storage_root.parent / "private-docs"
private_docs_root.joinpath("supplier-documents").mkdir(parents=True, exist_ok=True)
private_docs_root.joinpath("agent-documents").mkdir(parents=True, exist_ok=True)

register_api_routes(app)

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







