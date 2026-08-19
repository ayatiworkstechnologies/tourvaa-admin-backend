from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base

from app.models.admin_modules import AdminModule
from app.models.affiliate_tracking import AffiliateClick, AffiliateConversion, AffiliateLink, AffiliatePayout
from app.models.affiliates import Affiliate, AffiliateDocument, AffiliateInvoicing, AffiliateMarketingInfo
from app.models.agent_ledger import AgentLedger, AgentPayout, AgentPayoutItem
from app.models.agents import Agent, AgentBusinessInfo, AgentContact, AgentDocument, AgentInvoicing
from app.models.audit import AuditLog
from app.models.booking_calendar import BookingCalendarEvent
from app.models.bookings import Booking, BookingAccommodation, BookingCommunication, BookingExtension, BookingOptionalActivity, BookingStatusHistory, BookingTraveller, EmailLog, MessageReply
from app.models.cancellations import CancellationRequest, RefundRule
from app.models.chatbot import ChatEmbedding, ChatFAQ, ChatMessage, ChatSession
from app.models.checkout import CheckoutSession
from app.models.cms import City, Country, State, Tour, TourCategory, TourSubcategory, TourSubcategoryMap
from app.models.customers import Customer, CustomerCancellationRequest, CustomerCommunication, CustomerSavedTraveller, CustomerWishlistItem
from app.models.email_templates import EmailTemplate
from app.models.invoices import Invoice, InvoiceItem
from app.models.messaging import BookingConversation, BookingMessage, Conversation, Message
from app.models.notifications import Notification, NotificationLog, PushSubscription
from app.models.payments import Payment, PaymentHold, PaymentTransaction
from app.models.permissions import Permission, RolePermission
from app.models.public_leads import ContactMessage, NewsletterSubscriber
from app.models.reports import ReportSchedule
from app.models.reviews import TourReview
from app.models.roles import Role
from app.models.sessions import LoginHistory, UserSession
from app.models.settings import ApiSetting, AppSetting, PaymentSetting, SmtpSetting
from app.models.supplier_ledger import SupplierLedger, SupplierPayout, SupplierPayoutItem
from app.models.suppliers import Supplier, SupplierApprovalHistory, SupplierBusinessInfo, SupplierContact, SupplierDocument, SupplierInvoicing, SupplierVehicle
from app.models.tour_versions import TourReviewComment, TourVersion
from app.models.tours import (
    TourAccommodationExtra,
    TourCalendar,
    TourDiscount,
    TourExclusion,
    TourExtension,
    TourGalleryImage,
    TourHighlight,
    TourInclusion,
    TourItinerary,
    TourOptionalActivity,
    TourOverview,
    TourPricing,
    TourSimilar,
    TourUnavailableDate,
)
from app.models.users import User, UserRole, UserStatusHistory
from app.models.website_cms import Blog, CmsPolicy, CustomerReview, ExternalLink, HelpCentreArticle, HomepageBanner, PopularDestination, PopularTour, PromotionalPopup, SitemapEntry, TourOnDeal

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()


