from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.auth.cookies import csrf_cookie_name, portal_from_request, access_cookie_name

CSRF_HEADER_NAME = "X-CSRF-Token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Token refresh is exempt: it's issued automatically by the frontend's axios
# interceptor (no interceptor attaches a CSRF header to it), and a
# cross-site-forged refresh call only re-issues tokens for the victim's own
# already-authenticated session - it can't be used to make the attacker's
# forged request do anything the victim didn't already have a live session
# for, so it isn't a meaningful CSRF target.
EXEMPT_PATHS = {"/api/auth/refresh-token", "/api/auth/refresh", "/api/messages/mail-reply"}


class CsrfMiddleware(BaseHTTPMiddleware):
    """Double-submit-cookie CSRF check for cookie-authenticated requests.

    Login/refresh (`_set_auth_cookies` in app/routers/auth.py) issues a
    non-httponly `tourvaa_csrf` cookie alongside the httponly auth cookies.
    A same-origin page can read that cookie and echo it back as a header;
    a cross-site form/fetch cannot read it, so a mismatch means the request
    didn't originate from the app.

    Enforcement triggers whenever browser session cookies are used for
    mutating requests, preventing attackers from bypassing checks by
    stripping the CSRF cookie. Bearer-token clients remain unaffected.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in UNSAFE_METHODS and request.url.path not in EXEMPT_PATHS:
            portal = portal_from_request(request)
            auth_cookie = (
                request.cookies.get(access_cookie_name(portal))
                or request.cookies.get("tourvaa_access")
                or request.cookies.get("tourvaa_admin_access")
            )
            cookie_token = request.cookies.get(csrf_cookie_name(portal))
            if auth_cookie or cookie_token:
                header_token = request.headers.get(CSRF_HEADER_NAME)
                if not cookie_token or not header_token or header_token != cookie_token:
                    return JSONResponse(
                        status_code=403,
                        content={"status": "error", "message": "CSRF token missing or invalid"},
                    )
        return await call_next(request)
