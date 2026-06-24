from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base

from app.modules.admin_modules.models import AdminModule
from app.modules.affiliates.models import Affiliate, AffiliateDocument, AffiliateInvoicing, AffiliateMarketingInfo
from app.modules.agents.models import Agent, AgentBusinessInfo, AgentContact, AgentDocument, AgentInvoicing
from app.modules.audit.models import AuditLog
from app.modules.bookings.models import Booking, BookingAccommodation, BookingCommunication, BookingExtension, BookingOptionalActivity, BookingStatusHistory, BookingTraveller, EmailLog, MessageReply
from app.modules.chatbot.models import ChatFAQ, ChatMessage, ChatSession
from app.modules.cms.models import City, Country, Tour, TourCategory, TourSubcategory, TourSubcategoryMap
from app.modules.customers.models import Customer, CustomerCommunication
from app.modules.email_templates.models import EmailTemplate
from app.modules.invoices.models import Invoice, InvoiceItem
from app.modules.notifications.models import Notification, NotificationLog, PushSubscription
from app.modules.payments.models import Payment, PaymentHold, PaymentTransaction
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from app.modules.sessions.models import LoginHistory, UserSession
from app.modules.settings.models import ApiSetting, AppSetting, PaymentSetting
from app.modules.suppliers.models import Supplier, SupplierBusinessInfo, SupplierContact, SupplierDocument, SupplierInvoicing, SupplierVehicle
from app.modules.tours.models import (
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
from app.modules.users.models import User, UserRole

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


