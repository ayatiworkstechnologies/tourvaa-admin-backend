"""Viator business logic: configuration, destinations, categories, search
and outbound click analytics.

Nothing here reads or writes Tourvaa tours, pricing, bookings, payments,
invoices or supplier/agent ledgers - external products are displayed with
Viator's own price and booked on viator.com via the affiliate link.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from threading import Lock
from urllib.parse import urlencode

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.integrations.external_tours.constants import (
    PROVIDER_VIATOR,
    PROVIDERS,
    PUBLIC_CATEGORY,
    build_campaign,
    is_allowed_external_url,
    slugify_name,
    with_campaign,
)
from app.integrations.viator.client import ViatorClient, base_url_for
from app.integrations.viator.exceptions import ViatorError, ViatorNotConfigured, ViatorNotFound
from app.integrations.viator.mapper import normalize_product
from app.integrations.viator.schemas import ExternalClickRequest, ExternalTourSearchRequest
from app.models.cms import City, Country, State
from app.models.external_tours import ExternalAffiliateClick, ExternalDestinationMapping, ExternalProvider
from app.models.settings import ApiSetting
from app.utils.crypto import decrypt_secret

logger = logging.getLogger(__name__)

PROVIDER = PROVIDER_VIATOR

# Viator's top-level experience categories (tag ids from GET /products/tags).
# These ids are stable in Viator's taxonomy; the full tag list is ~1,300
# mostly niche entries, so the public filter uses this curated set.
CATEGORY_TAGS: list[tuple[int, str]] = [
    (21913, "Tours, Sightseeing & Cruises"),
    (21909, "Outdoor Activities"),
    (21910, "Art & Culture"),
    (21911, "Food & Drink"),
    (21912, "Tickets & Passes"),
    (21915, "Classes & Workshops"),
    (21916, "Seasonal & Special Occasions"),
    (21914, "Travel & Transportation Services"),
]
_CATEGORY_IDS = {tag_id for tag_id, _ in CATEGORY_TAGS}

_SORTS = {
    "recommended": None,  # Viator's DEFAULT ordering
    "rating": ("TRAVELER_RATING", "DESCENDING"),
    "price_asc": ("PRICE", "ASCENDING"),
    "price_desc": ("PRICE", "DESCENDING"),
    "duration": ("ITINERARY_DURATION", "ASCENDING"),
    "newest": ("DATE_ADDED", "DESCENDING"),
}

# Search results: short in-memory cache (prices/availability change, so
# never long). Destinations are cached in the DB by sync, not per request.
_SEARCH_TTL = timedelta(minutes=10)
_SEARCH_CACHE_MAX = 300
_search_cache: dict[str, tuple[datetime, dict]] = {}
_cache_lock = Lock()

# Name differences between Viator's and Tourvaa's country lists.
_COUNTRY_ALIASES = {
    "turkiye": "turkey",
    "netherlands": "the-netherlands",
    "czech-republic": "czechia",
    "united-states-of-america": "united-states",
    "usa": "united-states",
    "uk": "united-kingdom",
    "england": "united-kingdom",
    "scotland": "united-kingdom",
    "wales": "united-kingdom",
    "northern-ireland": "united-kingdom",
    "south-korea": "south-korea",
    "republic-of-ireland": "ireland",
    "vatican-city": "vatican",
    "macau": "macao",
    "cote-d-ivoire": "ivory-coast",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mask_tail(value: str, visible: int = 4) -> str:
    """'••••••••1a2b' - only ever the last few characters."""
    if not value:
        return ""
    return "•" * 8 + (value[-visible:] if len(value) > visible * 2 else "")


# --- configuration ------------------------------------------------------------

def _api_row(db: Session) -> ApiSetting | None:
    return db.query(ApiSetting).filter(ApiSetting.api_name == "viator").first()


def credentials(db: Session) -> tuple[str, str]:
    """(api_key, affiliate_pid): the admin-saved encrypted value wins, .env
    is the fallback. Never returned to any client."""
    row = _api_row(db)
    api_key = decrypt_secret(row.api_key if row else "") or settings.VIATOR_API_KEY
    pid = decrypt_secret(row.api_secret if row else "") or settings.VIATOR_PID or settings.VIATOR_AFFILIATE_PID
    return (api_key or "").strip(), (pid or "").strip()


def environment() -> str:
    return "production" if settings.VIATOR_ENV.strip().lower() == "production" else "sandbox"


def api_base_url() -> str:
    return base_url_for(environment(), settings.VIATOR_API_BASE_URL)


def admin_enabled(db: Session) -> bool:
    row = _api_row(db)
    return bool(row and row.is_enabled)


def is_enabled(db: Session) -> bool:
    """Both switches on and a key available."""
    api_key, _ = credentials(db)
    return bool(settings.VIATOR_ENABLED and admin_enabled(db) and api_key)


def get_client(db: Session) -> ViatorClient:
    if not is_enabled(db):
        raise ViatorNotConfigured("Viator is disabled or has no API key")
    api_key, _ = credentials(db)
    return ViatorClient(api_key, api_base_url(), timeout=settings.VIATOR_TIMEOUT_SECONDS)


def get_provider(db: Session) -> ExternalProvider:
    provider = db.query(ExternalProvider).filter(ExternalProvider.code == PROVIDER).first()
    if not provider:
        provider = ExternalProvider(code=PROVIDER, name=PROVIDERS[PROVIDER]["name"], public_category=PUBLIC_CATEGORY)
        db.add(provider)
        db.commit()
        db.refresh(provider)
    return provider


def public_config(db: Session) -> dict:
    """What the public site needs to decide where to show experiences."""
    provider = get_provider(db)
    enabled = is_enabled(db)
    return {
        "enabled": enabled,
        "provider": PROVIDER,
        "provider_name": provider.name,
        "public_category": provider.public_category or PUBLIC_CATEGORY,
        "attribution": PROVIDERS[PROVIDER]["attribution"],
        "show_on_homepage": enabled and provider.show_on_homepage,
        "show_on_destination_pages": enabled and provider.show_on_destination_pages,
        "show_on_itinerary": enabled and provider.show_on_itinerary,
        "show_in_search": enabled and provider.show_in_search,
    }


def categories() -> list[dict]:
    return [{"id": tag_id, "name": name} for tag_id, name in CATEGORY_TAGS]


# --- destinations -------------------------------------------------------------

def _serialize_destination(row: ExternalDestinationMapping, parent_name: str | None = None) -> dict:
    return {
        "slug": row.slug,
        "name": row.provider_destination_name,
        "type": row.provider_destination_type,
        "provider": row.provider,
        "provider_destination_id": row.provider_destination_id,
        "parent_name": parent_name,
        "tourvaa_country_id": row.tourvaa_country_id,
        "tourvaa_country_name": row.country.country_name if row.country else None,
        "tourvaa_city_id": row.tourvaa_city_id,
        "tourvaa_city_name": row.city.city_name if row.city else None,
    }


def _parent_names(db: Session, rows: list[ExternalDestinationMapping]) -> dict[str, str]:
    parent_ids = {r.provider_parent_destination_id for r in rows if r.provider_parent_destination_id}
    if not parent_ids:
        return {}
    parents = db.query(ExternalDestinationMapping.provider_destination_id, ExternalDestinationMapping.provider_destination_name).filter(
        ExternalDestinationMapping.provider == PROVIDER,
        ExternalDestinationMapping.provider_destination_id.in_(parent_ids),
    )
    return {pid: name for pid, name in parents}


def list_public_destinations(db: Session, search: str = "", limit: int = 20) -> list[dict]:
    """Search box / landing-page destinations. With no search term: the
    destinations linked to Tourvaa's own countries/cities come first."""
    q = db.query(ExternalDestinationMapping).filter(
        ExternalDestinationMapping.provider == PROVIDER,
        ExternalDestinationMapping.is_active.is_(True),
    )
    term = search.strip()
    if term:
        q = q.filter(ExternalDestinationMapping.provider_destination_name.ilike(f"%{term}%")).order_by(
            # exact / prefix matches first, cities before regions
            (func.lower(ExternalDestinationMapping.provider_destination_name) != term.lower()),
            ~ExternalDestinationMapping.provider_destination_name.ilike(f"{term}%"),
            (ExternalDestinationMapping.provider_destination_type != "CITY"),
            ExternalDestinationMapping.provider_destination_name,
        )
    else:
        # Featured: cities in the countries Tourvaa sells its own tours in
        # (cities that host a Tourvaa tour first), then those countries.
        from app.models.cms import Tour

        tour_geo = db.query(Tour.country_id, Tour.city_id).filter(Tour.status == "published").all()
        country_ids = {c for c, _ in tour_geo if c}
        city_ids = {c for _, c in tour_geo if c}
        if not country_ids:
            return []
        q = q.filter(
            ExternalDestinationMapping.tourvaa_country_id.in_(country_ids),
            or_(ExternalDestinationMapping.tourvaa_city_id.isnot(None),
                ExternalDestinationMapping.provider_destination_type == "COUNTRY"),
        ).order_by(
            (ExternalDestinationMapping.provider_destination_type == "COUNTRY"),
            ~ExternalDestinationMapping.tourvaa_city_id.in_(city_ids or {0}),
            ExternalDestinationMapping.provider_destination_name,
        )
    rows = q.limit(max(1, min(limit, 50))).all()
    names = _parent_names(db, rows)
    return [_serialize_destination(r, names.get(r.provider_parent_destination_id or "")) for r in rows]


def get_destination(db: Session, slug_or_id: str) -> ExternalDestinationMapping | None:
    q = db.query(ExternalDestinationMapping).filter(
        ExternalDestinationMapping.provider == PROVIDER,
        ExternalDestinationMapping.is_active.is_(True),
    )
    value = (slug_or_id or "").strip()
    if not value:
        return None
    if value.isdigit():
        row = q.filter(ExternalDestinationMapping.provider_destination_id == value).first()
        if row:
            return row
    return q.filter(ExternalDestinationMapping.slug == slugify_name(value)).first()


def public_destination(db: Session, slug_or_id: str) -> dict:
    row = get_destination(db, slug_or_id)
    if not row:
        raise ViatorNotFound(f"Unknown destination {slug_or_id!r}")
    return _serialize_destination(row, _parent_names(db, [row]).get(row.provider_parent_destination_id or ""))


def _country_mapping(db: Session, country: str) -> ExternalDestinationMapping | None:
    base = db.query(ExternalDestinationMapping).filter(
        ExternalDestinationMapping.provider == PROVIDER,
        ExternalDestinationMapping.is_active.is_(True),
        ExternalDestinationMapping.provider_destination_type == "COUNTRY",
    )
    by_tourvaa = base.join(Country, Country.id == ExternalDestinationMapping.tourvaa_country_id).filter(
        func.lower(Country.country_name) == country.strip().lower()
    ).first()
    return by_tourvaa or base.filter(ExternalDestinationMapping.slug == slugify_name(country)).first()


def resolve_destination(db: Session, *, destination: str | None = None, location: str | None = None, country: str | None = None) -> ExternalDestinationMapping | None:
    """slug / provider id first; otherwise a location name inside a country
    (e.g. itinerary day "Dubai" on a UAE tour), falling back to the country."""
    if destination:
        row = get_destination(db, destination)
        if row:
            return row
    country_row = _country_mapping(db, country) if country else None
    if location:
        name = location.split(",")[0].strip()
        q = db.query(ExternalDestinationMapping).filter(
            ExternalDestinationMapping.provider == PROVIDER,
            ExternalDestinationMapping.is_active.is_(True),
            func.lower(ExternalDestinationMapping.provider_destination_name) == name.lower(),
        )
        if country_row and country_row.tourvaa_country_id:
            q = q.filter(ExternalDestinationMapping.tourvaa_country_id == country_row.tourvaa_country_id)
        match = q.order_by(ExternalDestinationMapping.provider_destination_type != "CITY").first()
        if match:
            return match
    return country_row


def _normalize_country_key(name: str) -> str:
    key = slugify_name(name)
    return _COUNTRY_ALIASES.get(key, key)


def sync_destinations(db: Session) -> dict:
    """Pull Viator's destination taxonomy into external_destination_mappings
    and auto-link rows to Tourvaa countries/cities by name. Admin-set
    ("manual") links are never overwritten. Run manually from the admin
    screen; Viator recommends refreshing destinations about weekly."""
    provider = get_provider(db)
    client = get_client(db)
    try:
        payload = client.get_destinations()
    except ViatorError:
        provider.last_destination_sync_at = _now()
        provider.last_destination_sync_status = "error"
        db.commit()
        raise
    raw = [d for d in (payload.get("destinations") or []) if isinstance(d, dict) and d.get("destinationId") and d.get("name")]
    by_id = {str(d["destinationId"]): d for d in raw}

    # Tourvaa lookups for auto-matching.
    countries = {_normalize_country_key(name): cid for cid, name in db.query(Country.id, Country.country_name)}

    def country_of(dest_id: str, depth: int = 0) -> str | None:
        d = by_id.get(dest_id)
        if not d or depth > 8:
            return None
        if d.get("type") == "COUNTRY":
            return dest_id
        parent = d.get("parentDestinationId")
        return country_of(str(parent), depth + 1) if parent else None

    viator_country_to_tourvaa = {
        vid: countries.get(_normalize_country_key(d["name"]))
        for vid, d in by_id.items() if d.get("type") == "COUNTRY"
    }
    mapped_country_ids = {cid for cid in viator_country_to_tourvaa.values() if cid}
    cities: dict[tuple[int, str], tuple[int, int | None]] = {}
    if mapped_country_ids:
        for city_id, name, country_id, state_id in db.query(City.id, City.city_name, City.country_id, City.state_id).filter(City.country_id.in_(mapped_country_ids)):
            cities.setdefault((country_id, name.strip().lower()), (city_id, state_id))

    # Unique slugs: plain name when unique, else "<name>-<country>", else "-<id>".
    name_counts: dict[str, int] = {}
    for d in raw:
        key = slugify_name(d["name"])
        name_counts[key] = name_counts.get(key, 0) + 1
    slugs: dict[str, str] = {}
    used: set[str] = set()
    for vid, d in sorted(by_id.items(), key=lambda item: (item[1].get("type") != "COUNTRY", item[1].get("type") != "CITY", int(item[0]) if item[0].isdigit() else 0)):
        base = slugify_name(d["name"])
        slug = base
        if name_counts.get(base, 0) > 1 or slug in used:
            country_vid = country_of(vid)
            if country_vid and country_vid != vid:
                slug = f"{base}-{slugify_name(by_id[country_vid]['name'])}"
        if slug in used:
            slug = f"{base}-{vid}"
        used.add(slug)
        slugs[vid] = slug[:191]

    existing = {row.provider_destination_id: row for row in db.query(ExternalDestinationMapping).filter(ExternalDestinationMapping.provider == PROVIDER)}
    now = _now()
    created = updated = auto_mapped = 0
    # Clear slugs first so renames between rows can't trip the unique index.
    for row in existing.values():
        row.slug = f"__tmp__{row.id}"
    db.flush()

    for vid, d in by_id.items():
        row = existing.get(vid)
        if not row:
            row = ExternalDestinationMapping(provider=PROVIDER, provider_destination_id=vid)
            db.add(row)
            created += 1
        else:
            updated += 1
        row.provider_destination_name = d["name"][:255]
        row.provider_destination_type = (d.get("type") or None)
        row.provider_parent_destination_id = str(d["parentDestinationId"]) if d.get("parentDestinationId") else None
        row.provider_default_currency = (d.get("defaultCurrencyCode") or None)
        dest_url = d.get("destinationUrl")
        row.provider_destination_url = dest_url if is_allowed_external_url(dest_url, PROVIDER) else None
        row.slug = slugs[vid]
        row.is_active = True
        row.last_synced_at = now

        if row.mapping_source != "manual":
            country_vid = country_of(vid)
            tv_country = viator_country_to_tourvaa.get(country_vid) if country_vid else None
            tv_city = tv_state = None
            if tv_country and d.get("type") != "COUNTRY":
                match = cities.get((tv_country, d["name"].strip().lower()))
                if match:
                    tv_city, tv_state = match
            row.tourvaa_country_id = tv_country
            row.tourvaa_city_id = tv_city
            row.tourvaa_state_id = tv_state
            row.mapping_source = "auto" if tv_country else None
            if tv_country:
                auto_mapped += 1

    deactivated = 0
    for vid, row in existing.items():
        if vid not in by_id:
            row.is_active = False
            row.slug = f"removed-{row.provider_destination_id}"
            deactivated += 1

    provider.last_destination_sync_at = now
    provider.last_destination_sync_status = "success"
    provider.last_destination_sync_count = len(by_id)
    db.commit()
    return {"total": len(by_id), "created": created, "updated": updated, "deactivated": deactivated, "linked_to_tourvaa": auto_mapped}


# --- search -----------------------------------------------------------------

def build_search_payload(req: ExternalTourSearchRequest, provider_destination_id: str) -> dict:
    filtering: dict = {"destination": provider_destination_id}
    if req.category and req.category in _CATEGORY_IDS:
        filtering["tags"] = [req.category]
    if req.free_cancellation:
        filtering["flags"] = ["FREE_CANCELLATION"]
    if req.min_price is not None:
        filtering["lowestPrice"] = req.min_price
    if req.max_price is not None:
        filtering["highestPrice"] = req.max_price
    if req.start_date:
        filtering["startDate"] = req.start_date.isoformat()
    if req.end_date:
        filtering["endDate"] = req.end_date.isoformat()
    if req.min_rating:
        filtering["rating"] = {"from": req.min_rating, "to": 5}

    payload: dict = {
        "filtering": filtering,
        "pagination": {"start": (req.page - 1) * req.page_size + 1, "count": req.page_size},
        "currency": req.currency,
    }
    sort = _SORTS.get(req.sort)
    payload["sorting"] = {"sort": sort[0], "order": sort[1]} if sort else {"sort": "DEFAULT"}
    return payload


def _cache_get(key: str) -> dict | None:
    with _cache_lock:
        hit = _search_cache.get(key)
        if hit and hit[0] > _now():
            return hit[1]
        _search_cache.pop(key, None)
    return None


def _cache_set(key: str, value: dict) -> None:
    with _cache_lock:
        if len(_search_cache) >= _SEARCH_CACHE_MAX:
            for stale in sorted(_search_cache, key=lambda k: _search_cache[k][0])[: _SEARCH_CACHE_MAX // 4]:
                _search_cache.pop(stale, None)
        _search_cache[key] = (_now() + _SEARCH_TTL, value)


def clear_search_cache() -> None:
    with _cache_lock:
        _search_cache.clear()


def search(db: Session, req: ExternalTourSearchRequest, *, is_agent: bool = False) -> dict:
    destination = resolve_destination(db, destination=req.destination, location=req.location, country=req.country)
    if not destination:
        raise ViatorNotFound("Destination is not available")
    client = get_client(db)
    campaign = build_campaign(settings.VIATOR_CAMPAIGN_PREFIX, req.source, is_agent=is_agent)
    payload = build_search_payload(req, destination.provider_destination_id)

    cache_key = hashlib.sha256(json.dumps([payload, campaign, api_base_url()], sort_keys=True).encode()).hexdigest()
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    data = client.search_products(payload)
    raw_products = data.get("products") or [] if isinstance(data, dict) else []
    refs = {str(d.get("ref")) for p in raw_products if isinstance(p, dict) for d in (p.get("destinations") or []) if isinstance(d, dict) and d.get("ref")}
    names = dict(
        db.query(ExternalDestinationMapping.provider_destination_id, ExternalDestinationMapping.provider_destination_name)
        .filter(ExternalDestinationMapping.provider == PROVIDER, ExternalDestinationMapping.provider_destination_id.in_(refs))
    ) if refs else {}
    items = [p for p in (normalize_product(raw, campaign=campaign, destination_names=names) for raw in raw_products) if p]

    total = int(data.get("totalCount") or 0) if isinstance(data, dict) else 0
    result = {
        "items": items,
        "total": total,
        "page": req.page,
        "page_size": req.page_size,
        "total_pages": max(1, math.ceil(total / req.page_size)) if total else 1,
        "currency": req.currency,
        "destination": _serialize_destination(destination, _parent_names(db, [destination]).get(destination.provider_parent_destination_id or "")),
        "provider": {"code": PROVIDER, "name": PROVIDERS[PROVIDER]["name"], "attribution": PROVIDERS[PROVIDER]["attribution"]},
        "category": PUBLIC_CATEGORY,
    }
    _cache_set(cache_key, result)
    return result


# --- click analytics ----------------------------------------------------------

def record_click(db: Session, req: ExternalClickRequest, *, user_id: int | None, agent_id: int | None) -> ExternalAffiliateClick:
    """Store an outbound affiliate click. Analytics only - this is not a
    booking and nothing downstream (capacity, invoices, payments, payouts,
    agent commission) reads it."""
    if req.provider not in PROVIDERS:
        raise ValueError("Unknown provider")
    if not is_allowed_external_url(req.external_url, req.provider):
        raise ValueError("External URL is not an allowed provider link")
    campaign = build_campaign(settings.VIATOR_CAMPAIGN_PREFIX, req.source_page, is_agent=agent_id is not None)
    dest = get_destination(db, req.provider_destination_id) if req.provider_destination_id else None
    click = ExternalAffiliateClick(
        provider=req.provider,
        product_code=req.product_code,
        product_title=(req.product_title or None),
        provider_destination_id=req.provider_destination_id,
        tourvaa_country_id=dest.tourvaa_country_id if dest else None,
        tourvaa_city_id=dest.tourvaa_city_id if dest else None,
        user_id=user_id,
        agent_id=agent_id,
        session_id=req.session_id,
        campaign=campaign,
        source_page=req.source_page,
        page_path=req.page_path,
        external_url=req.external_url,
        external_url_hash=hashlib.sha256(req.external_url.encode()).hexdigest(),
    )
    db.add(click)
    db.commit()
    return click


# Viator's affiliate tracking id for partner links (constant for all partners).
VIATOR_MCID = "42383"


def day_trips_url(destination_id: str, destination_name: str, pid: str, campaign: str) -> str:
    """Viator's "Day Trips & Excursions" page for a destination on the live
    site, in Viator's own affiliate link format, e.g.
    https://www.viator.com/India-tours/Day-Trips-and-Excursions/d723-g5?pid=P00000000&mcid=42383&medium=link&campaign=...
    (g5 = Viator's Day Trips & Excursions category). Destination ids are the
    same in the sandbox and on the live site."""
    name = re.sub(r"[^A-Za-z0-9]+", "-", unicodedata.normalize("NFKD", destination_name).encode("ascii", "ignore").decode("ascii")).strip("-") or "destination"
    query = {"mcid": VIATOR_MCID, "medium": "link", "campaign": campaign}
    if pid:
        query = {"pid": pid, **query}
    return f"https://www.viator.com/{name}-tours/Day-Trips-and-Excursions/d{destination_id}-g5?{urlencode(query)}"


def destination_redirect(
    db: Session,
    *,
    destination: str | None,
    country: str | None,
    source: str,
    user_id: int | None,
    agent_id: int | None,
    session_id: str | None = None,
    page_path: str | None = None,
) -> dict:
    """Viator hand-off for a destination (homepage "Viator Day Tours &
    Experiences"): Viator's own affiliate destination URL (pid/mcid already
    in it) + our campaign, or the affiliate-tagged viator.com homepage when
    the destination isn't mapped. The outbound click is recorded here."""
    if not is_enabled(db):
        raise ViatorNotConfigured("Viator is disabled")
    campaign = build_campaign(settings.VIATOR_CAMPAIGN_PREFIX, source, is_agent=agent_id is not None)
    row = resolve_destination(db, destination=destination, country=country) if (destination or country) else None
    _, pid = credentials(db)
    if row:
        url = day_trips_url(row.provider_destination_id, row.provider_destination_name, pid, campaign)
    else:
        base = "https://www.viator.com/"
        url = f"{base}?{urlencode({'pid': pid, 'mcid': VIATOR_MCID, 'medium': 'link', 'campaign': campaign})}" if pid else base
    record_click(
        db,
        ExternalClickRequest(
            provider=PROVIDER,
            product_code=f"dest-{row.provider_destination_id}" if row else "viator-home",
            product_title=f"{row.provider_destination_name} (destination page)" if row else "Viator homepage",
            provider_destination_id=row.provider_destination_id if row else None,
            external_url=url,
            source_page=source,
            page_path=page_path,
            session_id=session_id,
        ),
        user_id=user_id,
        agent_id=agent_id,
    )
    return {"url": url, "destination": row.provider_destination_name if row else None}


# --- admin -----------------------------------------------------------------

def test_connection(db: Session) -> dict:
    provider = get_provider(db)
    try:
        client = get_client(db)
        sample = get_destination(db, "dubai")
        client.search_products({
            "filtering": {"destination": sample.provider_destination_id if sample else "828"},
            "pagination": {"start": 1, "count": 1},
            "currency": "USD",
        })
        provider.last_connection_status = "connected"
        provider.last_connection_message = f"Connected to the Viator {environment()} API"
    except ViatorNotConfigured:
        provider.last_connection_status = "disabled"
        provider.last_connection_message = "Viator is disabled or has no API key"
    except ViatorError as exc:
        provider.last_connection_status = "error"
        # Status code/category only - never the key or raw headers.
        provider.last_connection_message = f"{exc.code}" + (f" (HTTP {exc.status_code})" if exc.status_code else "")
    provider.last_connection_at = _now()
    db.commit()
    return admin_status(db)


def admin_status(db: Session) -> dict:
    provider = get_provider(db)
    api_key, pid = credentials(db)
    base = db.query(ExternalDestinationMapping).filter(ExternalDestinationMapping.provider == PROVIDER)
    total = base.filter(ExternalDestinationMapping.is_active.is_(True)).count()
    linked = base.filter(ExternalDestinationMapping.is_active.is_(True), ExternalDestinationMapping.tourvaa_country_id.isnot(None)).count()
    since = _now() - timedelta(days=30)
    clicks_30d = db.query(ExternalAffiliateClick).filter(ExternalAffiliateClick.provider == PROVIDER, ExternalAffiliateClick.created_at >= since).count()
    enabled = is_enabled(db)
    if not enabled:
        status = "disabled"
    elif provider.last_connection_status == "error":
        status = "error"
    elif provider.last_connection_status == "connected":
        status = "connected"
    else:
        status = "unknown"
    return {
        "provider": PROVIDER,
        "provider_name": provider.name,
        "public_category": provider.public_category,
        "status": status,
        "enabled": enabled,
        "admin_enabled": admin_enabled(db),
        "env_enabled": bool(settings.VIATOR_ENABLED),
        "environment": environment(),
        "api_base_url": api_base_url(),
        "api_key_configured": bool(api_key),
        "api_key_masked": mask_tail(api_key),
        "pid_configured": bool(pid),
        "pid_masked": mask_tail(pid, 3),
        "campaign_prefix": settings.VIATOR_CAMPAIGN_PREFIX,
        "tracking_enabled": True,
        "last_connection_status": provider.last_connection_status,
        "last_connection_message": provider.last_connection_message,
        "last_connection_at": provider.last_connection_at,
        "last_destination_sync_at": provider.last_destination_sync_at,
        "last_destination_sync_status": provider.last_destination_sync_status,
        "destination_count": total,
        "destinations_linked_to_tourvaa": linked,
        "destination_mapping": "configured" if linked else "missing",
        "clicks_last_30_days": clicks_30d,
        "settings": {
            "show_on_homepage": provider.show_on_homepage,
            "show_on_destination_pages": provider.show_on_destination_pages,
            "show_on_itinerary": provider.show_on_itinerary,
            "show_in_search": provider.show_in_search,
        },
    }


def update_provider_settings(db: Session, data: dict) -> dict:
    provider = get_provider(db)
    for key in ("show_on_homepage", "show_on_destination_pages", "show_on_itinerary", "show_in_search"):
        if data.get(key) is not None:
            setattr(provider, key, bool(data[key]))
    db.commit()
    return admin_status(db)


def _serialize_mapping(row: ExternalDestinationMapping, parent_name: str | None = None) -> dict:
    return {
        "id": row.id,
        **_serialize_destination(row, parent_name),
        "tourvaa_state_id": row.tourvaa_state_id,
        "tourvaa_state_name": row.state.state_name if row.state else None,
        "mapping_source": row.mapping_source,
        "is_active": row.is_active,
        "last_synced_at": row.last_synced_at,
    }


def list_mappings(db: Session, *, search: str = "", status: str = "", dest_type: str = "", page: int = 1, limit: int = 25) -> dict:
    q = db.query(ExternalDestinationMapping).filter(ExternalDestinationMapping.provider == PROVIDER)
    if search.strip():
        q = q.filter(ExternalDestinationMapping.provider_destination_name.ilike(f"%{search.strip()}%"))
    if status == "linked":
        q = q.filter(ExternalDestinationMapping.tourvaa_country_id.isnot(None))
    elif status == "unlinked":
        q = q.filter(ExternalDestinationMapping.tourvaa_country_id.is_(None))
    elif status == "manual":
        q = q.filter(ExternalDestinationMapping.mapping_source == "manual")
    elif status == "inactive":
        q = q.filter(ExternalDestinationMapping.is_active.is_(False))
    if dest_type:
        q = q.filter(ExternalDestinationMapping.provider_destination_type == dest_type.upper())
    total = q.count()
    rows = (
        q.order_by(ExternalDestinationMapping.tourvaa_country_id.is_(None), ExternalDestinationMapping.provider_destination_name)
        .offset((page - 1) * limit).limit(limit).all()
    )
    names = _parent_names(db, rows)
    return {
        "items": [_serialize_mapping(r, names.get(r.provider_parent_destination_id or "")) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, math.ceil(total / limit)),
    }


def update_mapping(db: Session, mapping_id: int, data: dict) -> dict:
    row = db.query(ExternalDestinationMapping).filter(ExternalDestinationMapping.id == mapping_id, ExternalDestinationMapping.provider == PROVIDER).first()
    if not row:
        raise ViatorNotFound("Mapping not found")
    if data.get("reset_to_auto"):
        row.tourvaa_country_id = row.tourvaa_state_id = row.tourvaa_city_id = None
        row.mapping_source = None
    else:
        country_id = data.get("tourvaa_country_id")
        state_id = data.get("tourvaa_state_id")
        city_id = data.get("tourvaa_city_id")
        if city_id:
            city = db.query(City).filter(City.id == city_id).first()
            if not city:
                raise ValueError("City not found")
            country_id = country_id or city.country_id
            state_id = state_id or city.state_id
            if city.country_id != country_id:
                raise ValueError("City does not belong to the selected country")
        if state_id and not db.query(State).filter(State.id == state_id).first():
            raise ValueError("State not found")
        if country_id and not db.query(Country).filter(Country.id == country_id).first():
            raise ValueError("Country not found")
        if any(k in data for k in ("tourvaa_country_id", "tourvaa_state_id", "tourvaa_city_id")):
            row.tourvaa_country_id = country_id
            row.tourvaa_state_id = state_id
            row.tourvaa_city_id = city_id
            row.mapping_source = "manual"
    if data.get("is_active") is not None:
        row.is_active = bool(data["is_active"])
    db.commit()
    db.refresh(row)
    return _serialize_mapping(row, _parent_names(db, [row]).get(row.provider_parent_destination_id or ""))


def click_summary(db: Session, days: int = 30) -> dict:
    since = _now() - timedelta(days=max(1, min(days, 365)))
    base = db.query(ExternalAffiliateClick).filter(ExternalAffiliateClick.provider == PROVIDER, ExternalAffiliateClick.created_at >= since)

    def grouped(col, limit=10):
        return [
            {"key": key, "clicks": count}
            for key, count in base.with_entities(col, func.count(ExternalAffiliateClick.id)).group_by(col).order_by(func.count(ExternalAffiliateClick.id).desc()).limit(limit)
        ]

    top_products = [
        {"product_code": code, "title": title, "clicks": count}
        for code, title, count in base.with_entities(
            ExternalAffiliateClick.product_code,
            func.max(ExternalAffiliateClick.product_title),
            func.count(ExternalAffiliateClick.id),
        ).group_by(ExternalAffiliateClick.product_code).order_by(func.count(ExternalAffiliateClick.id).desc()).limit(10)
    ]
    return {
        "days": days,
        "total": base.count(),
        "logged_in": base.filter(ExternalAffiliateClick.user_id.isnot(None)).count(),
        "agents": base.filter(ExternalAffiliateClick.agent_id.isnot(None)).count(),
        "by_source": grouped(ExternalAffiliateClick.source_page),
        "by_campaign": grouped(ExternalAffiliateClick.campaign),
        "by_destination": [
            {**item, "name": get_destination(db, item["key"]).provider_destination_name if item["key"] and get_destination(db, item["key"]) else None}
            for item in grouped(ExternalAffiliateClick.provider_destination_id)
        ],
        "top_products": top_products,
    }
