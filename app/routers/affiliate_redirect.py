"""Public, unauthenticated affiliate short-link redirect: GET /r/{code}.

Deliberately mounted directly on the app (not under /api and not through
app/api/router.py's register_api_routes) so it stays reachable as a short,
shareable URL - https://tourvaa.com/r/{code} - matching what an affiliate
actually pastes into a social post. The frontend's next.config.ts rewrites
/r/:path* to this same backend, so the browser never needs to know the
backend's real origin.
"""
import logging
import secrets
from datetime import timedelta

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.affiliate_tracking import AffiliateAttribution, AffiliateClick, AffiliateLink
from app.models.affiliates import Affiliate
from app.utils.money import utcnow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Affiliate Redirect"])

COOKIE_NAME = "tourvaa_affiliate_ref"
DEFAULT_FALLBACK = "/"


def _resolve_link(db: Session, code: str):
    return (
        db.query(AffiliateLink)
        .filter((AffiliateLink.ref_code == code) | (AffiliateLink.custom_alias == code))
        .first()
    )


def _destination_for(link: AffiliateLink) -> str:
    if link.link_type == "tour" and link.tour_id and link.tour:
        return f"/tours/{link.tour.slug}"
    return link.destination_url or DEFAULT_FALLBACK


def _is_trackable(link: AffiliateLink) -> bool:
    if link.status != "active":
        return False
    affiliate = link.affiliate
    if not affiliate or (affiliate.status or "").lower() != "active":
        return False
    now = utcnow()
    if link.valid_from and link.valid_from > now:
        return False
    if link.valid_until and link.valid_until < now:
        return False
    return True


@router.get("/r/{code}")
def redirect_affiliate_link(code: str, request: Request):
    db = SessionLocal()
    try:
        link = _resolve_link(db, code)
        if not link:
            return RedirectResponse(url=DEFAULT_FALLBACK, status_code=302)

        destination = _destination_for(link)

        # Disabled/expired links must keep working as plain links (spec:
        # never break an already-shared URL) but stop generating new
        # tracking data once admin has turned them off.
        if not _is_trackable(link):
            return RedirectResponse(url=destination, status_code=302)

        visitor_token = request.cookies.get(COOKIE_NAME) or secrets.token_urlsafe(24)
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        referrer = request.headers.get("referer")

        click = AffiliateClick(link_id=link.id, affiliate_id=link.affiliate_id, ip_address=ip, user_agent=ua, referrer=referrer)
        db.add(click)
        db.flush()

        now = utcnow()
        existing = (
            db.query(AffiliateAttribution)
            .filter(AffiliateAttribution.visitor_id == visitor_token, AffiliateAttribution.status == "active", AffiliateAttribution.expires_at > now)
            .order_by(AffiliateAttribution.attributed_at.desc())
            .first()
        )
        # First-click: an existing unexpired first-click attribution for this
        # visitor is never overwritten by a later click, regardless of which
        # link/affiliate the new click belongs to. Last-click (default):
        # every trackable click supersedes the prior attribution.
        if not (existing and existing.attribution_model == "first_click"):
            window_days = link.attribution_window_days or 30
            db.add(AffiliateAttribution(
                affiliate_id=link.affiliate_id,
                affiliate_link_id=link.id,
                affiliate_click_id=click.id,
                visitor_id=visitor_token,
                attribution_model=link.attribution_model or "last_click",
                expires_at=now + timedelta(days=window_days),
                status="active",
            ))

        db.commit()

        response = RedirectResponse(url=destination, status_code=302)
        max_age = (link.attribution_window_days or 30) * 86400
        response.set_cookie(
            key=COOKIE_NAME,
            value=visitor_token,
            max_age=max_age,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
        return response
    except Exception:
        logger.exception("Affiliate redirect failed for code=%s", code)
        db.rollback()
        return RedirectResponse(url=DEFAULT_FALLBACK, status_code=302)
    finally:
        db.close()
