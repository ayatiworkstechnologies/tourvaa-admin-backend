from fastapi import FastAPI

from app.routers.admin_modules import router as admin_modules_router
from app.routers.affiliates import router as affiliates_router
from app.routers.affiliate_tracking import router as affiliate_tracking_router
from app.routers.agents import router as agents_router
from app.routers.audit import alias_router as audit_logs_alias_router
from app.routers.audit import router as activity_logs_router
from app.routers.auth import router as auth_router
from app.routers.booking_calendar import router as booking_calendar_router
from app.routers.bookings import agent_portal_router as bookings_agent_portal_router
from app.routers.bookings import router as bookings_router
from app.routers.bookings import supplier_portal_router as bookings_supplier_portal_router
from app.routers.bookings import supplier_router as bookings_supplier_router
from app.routers.cancellations import router as cancellations_router
from app.routers.chatbot import router as chatbot_router
from app.routers.checkout import router as checkout_router
from app.routers.client import router as client_router
from app.routers.cms_geo import router as geo_router
from app.routers.cms_geo_seed import router as geo_seed_router
from app.routers.cms import router as cms_router
from app.routers.customers_portal import router as customer_portal_router
from app.routers.customers import router as customers_router
from app.routers.dashboard import router as dashboard_router
from app.routers.email_templates import router as email_templates_router
from app.routers.invoices import router as invoices_router
from app.routers.notifications import router as notifications_router
from app.routers.payments_gateway import router as payments_gateway_router
from app.routers.payments import router as payments_router
from app.routers.permissions import router as permissions_router
from app.routers.private_documents import router as private_documents_router
from app.routers.profile import router as profile_router
from app.routers.public import router as public_router
from app.routers.reports import router as reports_router
from app.routers.roles import router as roles_router
from app.routers.sessions import router as sessions_router
from app.routers.settings import router as settings_router
from app.routers.supplier_ledger import router as supplier_ledger_router
from app.routers.suppliers import router as suppliers_router
from app.routers.tour_versions import router as tour_versions_router
from app.routers.tours import discounts_router
from app.routers.tours import router as tour_detail_router
from app.routers.uploads import router as uploads_router
from app.routers.users import router as users_router
from app.routers.website_cms import router as website_cms_router

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
    # Static /tours/pending-approval must be registered before CMS /tours/{tour_id}.
    tour_versions_router,
    cms_router,
    geo_seed_router,
    geo_router,
    website_cms_router,
)

OPERATIONS_ROUTERS = (
    bookings_router,
    # Static gateway paths such as /payments/paypal/capture must precede
    # /payments/{payment_id}/capture from the core payments router.
    payments_gateway_router,
    payments_router,
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
