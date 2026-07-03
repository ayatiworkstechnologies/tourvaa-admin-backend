from fastapi import FastAPI

from app.modules.admin_modules.router import router as admin_modules_router
from app.modules.affiliates.router import router as affiliates_router
from app.modules.affiliate_tracking.router import router as affiliate_tracking_router
from app.modules.agents.router import router as agents_router
from app.modules.audit.router import alias_router as audit_logs_alias_router
from app.modules.audit.router import router as activity_logs_router
from app.modules.auth.router import router as auth_router
from app.modules.booking_calendar.router import router as booking_calendar_router
from app.modules.bookings.router import agent_portal_router as bookings_agent_portal_router
from app.modules.bookings.router import router as bookings_router
from app.modules.bookings.router import supplier_portal_router as bookings_supplier_portal_router
from app.modules.bookings.router import supplier_router as bookings_supplier_router
from app.modules.cancellations.router import router as cancellations_router
from app.modules.chatbot.router import router as chatbot_router
from app.modules.checkout.router import router as checkout_router
from app.modules.client.router import router as client_router
from app.modules.cms.geo_router import router as geo_router
from app.modules.cms.geo_seed_router import router as geo_seed_router
from app.modules.cms.router import router as cms_router
from app.modules.customers.customer_router import router as customer_portal_router
from app.modules.customers.router import router as customers_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.email_templates.router import router as email_templates_router
from app.modules.invoices.router import router as invoices_router
from app.modules.notifications.router import router as notifications_router
from app.modules.payments.gateway_router import router as payments_gateway_router
from app.modules.payments.router import router as payments_router
from app.modules.permissions.router import router as permissions_router
from app.modules.private_documents.router import router as private_documents_router
from app.modules.profile.router import router as profile_router
from app.modules.public.router import router as public_router
from app.modules.reports.router import router as reports_router
from app.modules.roles.router import router as roles_router
from app.modules.sessions.router import router as sessions_router
from app.modules.settings.router import router as settings_router
from app.modules.supplier_ledger.router import router as supplier_ledger_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.tour_versions.router import router as tour_versions_router
from app.modules.tours.router import discounts_router
from app.modules.tours.router import router as tour_detail_router
from app.modules.uploads.router import router as uploads_router
from app.modules.users.router import router as users_router
from app.modules.website_cms.router import router as website_cms_router

API_PREFIX = "/api"

CORE_ROUTERS = (
    auth_router,
    users_router,
    roles_router,
    permissions_router,
    admin_modules_router,
    dashboard_router,
    profile_router,
    settings_router,
    email_templates_router,
    uploads_router,
    client_router,
)

PARTNER_AND_CUSTOMER_ROUTERS = (
    customers_router,
    customer_portal_router,
    suppliers_router,
    agents_router,
    affiliates_router,
)

CONTENT_AND_TOUR_ROUTERS = (
    tour_detail_router,
    discounts_router,
    cms_router,
    geo_seed_router,
    geo_router,
    website_cms_router,
    tour_versions_router,
)

OPERATIONS_ROUTERS = (
    bookings_router,
    payments_router,
    payments_gateway_router,
    invoices_router,
    notifications_router,
    reports_router,
    sessions_router,
    activity_logs_router,
    audit_logs_alias_router,
    bookings_supplier_router,
    bookings_supplier_portal_router,
    bookings_agent_portal_router,
    chatbot_router,
    supplier_ledger_router,
    checkout_router,
    cancellations_router,
    booking_calendar_router,
    affiliate_tracking_router,
    private_documents_router,
)

ADMIN_ALIAS_ROUTERS = (
    roles_router,
    permissions_router,
)


def register_api_routes(app: FastAPI) -> None:
    for router in (
        *CORE_ROUTERS,
        *PARTNER_AND_CUSTOMER_ROUTERS,
        *CONTENT_AND_TOUR_ROUTERS,
        *OPERATIONS_ROUTERS,
    ):
        app.include_router(router, prefix=API_PREFIX)

    for router in ADMIN_ALIAS_ROUTERS:
        app.include_router(router, prefix=f"{API_PREFIX}/admin")

    app.include_router(public_router, prefix=f"{API_PREFIX}/public")
