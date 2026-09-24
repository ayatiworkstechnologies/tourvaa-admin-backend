"""Legacy Viator entry points (GET /public/external-day-trips and
/public/viator/redirect-url), kept for backward compatibility.

All real work now lives in app/integrations/viator (see its service.py);
these wrappers only adapt the old response shapes. The public site uses
/public/external-tours/* and the /day-tours pages instead.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.integrations.external_tours.constants import build_campaign
from app.integrations.viator import service as viator_service
from app.integrations.viator.exceptions import ViatorError
from app.integrations.viator.schemas import ExternalTourSearchRequest

logger = logging.getLogger(__name__)

VIATOR_SITE_BASE = "https://www.viator.com"

# Queenstown, New Zealand - the legacy page's fixed destination.
DEFAULT_DESTINATION_ID = "407"
DEFAULT_DESTINATION_NAME = "Queenstown, New Zealand"


def _credentials(db: Session) -> tuple[str, str]:
    return viator_service.credentials(db)


def is_configured(db: Session) -> bool:
    return viator_service.is_enabled(db)


def build_generic_affiliate_url(affiliate_pid: str) -> str:
    """Affiliate-tagged viator.com homepage link for hand-offs that aren't
    about one product. There is no API-provided URL for this case, so it is
    the one place a Viator link is composed by hand."""
    if not affiliate_pid:
        return VIATOR_SITE_BASE
    campaign = build_campaign(settings.VIATOR_CAMPAIGN_PREFIX, "home")
    return f"{VIATOR_SITE_BASE}/?pid={affiliate_pid}&mcid=42383&medium=link&campaign={campaign}"


def search_day_trips(db: Session, destination_id: str = DEFAULT_DESTINATION_ID, count: int = 12, force: bool = False) -> dict:
    """Old response shape, backed by the new search. Never raises."""
    if not is_configured(db):
        return {"products": [], "destination_name": DEFAULT_DESTINATION_NAME, "stale": False}
    try:
        result = viator_service.search(
            db,
            ExternalTourSearchRequest(destination=destination_id, sort="rating", page_size=min(count, 24), source="day-tours"),
        )
    except ViatorError as exc:
        logger.warning("Legacy Viator day-trip search failed: %s", exc.code)
        return {"products": [], "destination_name": DEFAULT_DESTINATION_NAME, "stale": True}
    products = [
        {
            "product_code": item["product_code"],
            "title": item["title"],
            "description": item["short_description"],
            "image_url": item["image"],
            "rating": item["rating"],
            "review_count": item["review_count"],
            "from_price": item["from_price"],
            "currency": item["currency"],
            "duration_label": item["duration"],
            "booking_url": item["external_url"],
        }
        for item in result["items"]
    ]
    return {"products": products, "destination_name": result["destination"]["name"] or DEFAULT_DESTINATION_NAME, "stale": False}
