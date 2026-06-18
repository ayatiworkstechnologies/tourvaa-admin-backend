from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base

from app.modules.audit.models import AuditLog
from app.modules.email_templates.models import EmailTemplate
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from app.modules.settings.models import AppSetting
from app.modules.users.models import User
from app.modules.bookings.models import Booking
from app.modules.payments.models import Payment
from app.modules.tours.models import (
    TourOverview, TourItinerary, TourInclusion, TourExclusion, TourHighlight,
    TourSimilar, TourExtension, TourGalleryImage,
    TourPricing, TourOptionalActivity, TourAccommodationExtra,
    TourCalendar, TourUnavailableDate, TourDiscount,
)

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
