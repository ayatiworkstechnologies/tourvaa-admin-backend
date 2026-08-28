"""Viator Partner API (Basic Access) - "External Day Trips" public section.

Read-only integration: we search Viator's product catalog for one fixed
destination and surface it as cards that deep-link out to viator.com to
complete the booking there (Tourvaa never touches the transaction). Basic
Access does not require pre-authorization, but it does require a real
exp-api-key from the Viator Partner dashboard (Settings -> API Keys).

Credentials live in the api_settings DB table (api_name="viator",
api_key=exp-api-key, api_secret=affiliate Partner ID) so they're editable
from Admin -> Settings -> API Settings, same as the other third-party keys
(see app/services/settings.py). VIATOR_API_KEY / VIATOR_AFFILIATE_PID in
.env are a fallback only, for environments without DB access (scripts, CI).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from threading import Lock

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.settings import ApiSetting
from app.utils.crypto import decrypt_secret

logger = logging.getLogger(__name__)

VIATOR_API_BASE = "https://api.viator.com/partner"
VIATOR_SITE_BASE = "https://www.viator.com"

# Queenstown, New Zealand - matches Tourvaa's own strongest tour market
# (Milford Sound / Fiordland day trips). Swap this single constant to move
# the section to a different Viator destination later.
DEFAULT_DESTINATION_ID = "407"
DEFAULT_DESTINATION_NAME = "Queenstown, New Zealand"

_CACHE_TTL = timedelta(minutes=30)
_cache_lock = Lock()
_cache: dict[str, object] = {}


def _credentials(db: Session) -> tuple[str, str]:
    """(api_key, affiliate_pid), DB row taking priority over env fallback."""
    row = db.query(ApiSetting).filter(ApiSetting.api_name == "viator").first()
    api_key = decrypt_secret(row.api_key if row else "") or settings.VIATOR_API_KEY
    pid = decrypt_secret(row.api_secret if row else "") or settings.VIATOR_AFFILIATE_PID
    return api_key or "", pid or ""


def is_configured(db: Session) -> bool:
    api_key, _ = _credentials(db)
    return bool(api_key)


def _headers(api_key: str) -> dict[str, str]:
    return {
        "exp-api-key": api_key,
        "Accept": "application/json;version=2.0",
        "Accept-Language": "en-US",
        "Content-Type": "application/json",
    }


def build_generic_affiliate_url(affiliate_pid: str) -> str:
    """Affiliate-tagged link to viator.com's homepage, for hand-offs that
    aren't about one specific product (e.g. the "Viator" duration option) --
    same pid/mcid/medium/campaign convention as build_affiliate_url below."""
    if not affiliate_pid:
        return VIATOR_SITE_BASE
    return f"{VIATOR_SITE_BASE}/?pid={affiliate_pid}&mcid=42383&medium=link&campaign=external-day-trips"


def build_affiliate_url(product_url: str | None, product_code: str, affiliate_pid: str) -> str:
    """Deep-link out to viator.com, tagged with the affiliate PID when we have one.

    Without an affiliate PID the link still works, it just isn't attributed
    to this account for commission.
    """
    url = product_url or f"{VIATOR_SITE_BASE}/tours/{product_code}"
    if not affiliate_pid:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}pid={affiliate_pid}&mcid=42383&medium=link&campaign=external-day-trips"


def _serialize_product(item: dict, affiliate_pid: str) -> dict | None:
    product_code = item.get("productCode")
    title = item.get("title")
    if not product_code or not title:
        return None

    images = item.get("images") or []
    image_url = None
    if images and isinstance(images[0], dict):
        variants = images[0].get("variants") or []
        largest = max(variants, key=lambda v: v.get("width", 0), default=None) if variants else None
        image_url = (largest or {}).get("url")

    reviews = item.get("reviews") or {}
    pricing = item.get("pricing") or {}
    summary_pricing = pricing.get("summary") or {}
    duration = item.get("duration") or {}

    return {
        "product_code": product_code,
        "title": title,
        "description": item.get("description"),
        "image_url": image_url,
        "rating": reviews.get("combinedAverageRating"),
        "review_count": reviews.get("totalReviews"),
        "from_price": summary_pricing.get("fromPrice"),
        "currency": pricing.get("currency"),
        "duration_label": duration.get("description") if isinstance(duration, dict) else None,
        "booking_url": build_affiliate_url(item.get("productUrl"), product_code, affiliate_pid),
    }


def search_day_trips(
    db: Session,
    destination_id: str = DEFAULT_DESTINATION_ID,
    count: int = 12,
    force: bool = False,
) -> dict:
    """Cached product search for one destination. Never raises - callers
    always get a usable (possibly empty) payload so a Viator outage or a
    missing/expired API key can't take down the public page."""
    cache_key = f"{destination_id}:{count}"
    now = datetime.now(timezone.utc)

    if not force:
        with _cache_lock:
            cached = _cache.get(cache_key)
            if isinstance(cached, dict) and cached.get("expires_at", now) > now:
                return {"products": cached["products"], "destination_name": cached["destination_name"], "stale": False}

    api_key, affiliate_pid = _credentials(db)
    if not api_key:
        return {"products": [], "destination_name": DEFAULT_DESTINATION_NAME, "stale": False}

    try:
        response = httpx.post(
            f"{VIATOR_API_BASE}/products/search",
            headers=_headers(api_key),
            json={
                "filtering": {"destination": destination_id},
                "sorting": {"sort": "TRAVELER_RATING", "order": "DESCENDING"},
                "pagination": {"start": 1, "count": count},
                "currency": "USD",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        raw_products = payload.get("products") or []
        products = [p for p in (_serialize_product(item, affiliate_pid) for item in raw_products) if p]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Viator product search failed for destination %s: %s", destination_id, exc)
        with _cache_lock:
            cached = _cache.get(cache_key)
        if isinstance(cached, dict):
            return {"products": cached["products"], "destination_name": cached["destination_name"], "stale": True}
        return {"products": [], "destination_name": DEFAULT_DESTINATION_NAME, "stale": True}

    with _cache_lock:
        _cache[cache_key] = {
            "products": products,
            "destination_name": DEFAULT_DESTINATION_NAME,
            "expires_at": now + _CACHE_TTL,
        }

    return {"products": products, "destination_name": DEFAULT_DESTINATION_NAME, "stale": False}
