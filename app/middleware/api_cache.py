"""Response headers for live API data.

The portal is a transactional application: stale bookings, payments, balances
or availability are worse than a small amount of extra network traffic.  Send
an explicit no-store policy from the API itself, in addition to the frontend
request policy, so browsers and intermediary proxies agree.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class ApiNoStoreMiddleware(BaseHTTPMiddleware):
    """Prevent browser/proxy caching of dynamic ``/api`` responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
