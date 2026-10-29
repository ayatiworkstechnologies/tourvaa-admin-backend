"""Browser cookie names for the isolated admin session.

Customer, supplier, agent and affiliate remain on the established shared
browser session. Admin uses a distinct cookie triplet so back-office access
can coexist with one of those portal sessions in the same browser profile.
"""
from fastapi import Request

PORTAL_HEADER_NAME = "X-Tourvaa-Portal"


def portal_from_request(request: Request) -> str | None:
    portal = (request.headers.get(PORTAL_HEADER_NAME) or "").strip().lower()
    return "admin" if portal == "admin" else None


def access_cookie_name(portal: str | None) -> str:
    return "tourvaa_admin_access" if portal == "admin" else "tourvaa_access"


def refresh_cookie_name(portal: str | None) -> str:
    return "tourvaa_admin_refresh" if portal == "admin" else "tourvaa_refresh"


def csrf_cookie_name(portal: str | None) -> str:
    return "tourvaa_admin_csrf" if portal == "admin" else "tourvaa_csrf"
