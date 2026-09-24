"""Shared constants and helpers for external (affiliate) inventory."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Inventory source / booking behaviour. Tourvaa's own tours are implicitly
# TOURVAA + INTERNAL; external products are always AFFILIATE_REDIRECT.
SOURCE_TOURVAA = "TOURVAA"
BOOKING_INTERNAL = "INTERNAL"
BOOKING_AFFILIATE_REDIRECT = "AFFILIATE_REDIRECT"

# Internal/admin code for this inventory type, and what customers see.
INVENTORY_CODE = "EXTERNAL_DAY_TRIPS"
PUBLIC_CATEGORY = "Day Tours & Experiences"

PROVIDER_VIATOR = "VIATOR"

# Provider registry. Adding GETYOURGUIDE/KLOOK later = a new entry here plus
# its own integration package; the public API/UI stay provider-agnostic.
PROVIDERS: dict[str, dict] = {
    PROVIDER_VIATOR: {
        "code": PROVIDER_VIATOR,
        "name": "Viator",
        "attribution": "Powered by Viator",
        # Hosts an outbound affiliate link may point at (sandbox links use
        # shop.live.rc.viator.com).
        "allowed_hosts": ("viator.com",),
    },
}

# Where a click/search came from -> campaign suffix (tourvaa-<suffix>).
CAMPAIGN_SOURCES = (
    "home",
    "day-tours",
    "destination",
    "tour-detail",
    "free-day",
    "agent",
    "mobile",
)
DEFAULT_CAMPAIGN_SOURCE = "day-tours"


def is_known_provider(code: str | None) -> bool:
    return bool(code) and code.upper() in PROVIDERS


def build_campaign(prefix: str, source: str | None, *, is_agent: bool = False) -> str:
    """Shared campaign naming: <prefix>-<source>, e.g. tourvaa-destination.
    Agents always get <prefix>-agent so their traffic is separable."""
    suffix = "agent" if is_agent else (source if source in CAMPAIGN_SOURCES else DEFAULT_CAMPAIGN_SOURCE)
    clean_prefix = re.sub(r"[^a-z0-9-]+", "", (prefix or "tourvaa").lower()) or "tourvaa"
    return f"{clean_prefix}-{suffix}"


def is_allowed_external_url(url: str | None, provider: str = PROVIDER_VIATOR) -> bool:
    """Only https links on the provider's own domain may be sent to / opened
    by the browser - never an arbitrary redirect target."""
    if not url or not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme != "https" or not parts.hostname:
        return False
    host = parts.hostname.lower()
    allowed = PROVIDERS.get(provider.upper(), {}).get("allowed_hosts", ())
    return any(host == h or host.endswith("." + h) for h in allowed)


def with_campaign(url: str, campaign: str) -> str:
    """Add campaign=<value> to a provider affiliate URL, keeping every
    existing query parameter (pid, mcid, medium, ...) exactly as returned.
    Never rebuilds the URL from scratch and never drops parameters; if the
    provider already set a campaign it is left alone."""
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if any(key == "campaign" for key, _ in query):
        return url
    separator = "&" if parts.query else ""
    new_query = f"{parts.query}{separator}{urlencode({'campaign': campaign})}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


# Viator's sandbox API returns links to its test storefront. Customers must
# always land on the real site, so that host is swapped for www.viator.com.
# Everything else (path, pid, mcid, campaign ...) is kept exactly as returned;
# production links already point at www.viator.com and pass through untouched.
VIATOR_SANDBOX_SITE_HOSTS = ("shop.live.rc.viator.com",)
VIATOR_LIVE_SITE_HOST = "www.viator.com"


def to_live_site(url: str, destination_name: str | None = None) -> str:
    parts = urlsplit(url)
    if (parts.hostname or "").lower() not in VIATOR_SANDBOX_SITE_HOSTS:
        return url
    path = parts.path
    # Sandbox destination links use a placeholder segment ("/x/d4452-ttd");
    # the live site's format is "/<Destination-Name>/d4452-ttd".
    if destination_name and path.startswith("/x/"):
        name = re.sub(r"[^A-Za-z0-9]+", "-", unicodedata.normalize("NFKD", destination_name).encode("ascii", "ignore").decode("ascii")).strip("-")
        if name:
            path = f"/{name}/{path[3:]}"
    return urlunsplit((parts.scheme, VIATOR_LIVE_SITE_HOST, path, parts.query, parts.fragment))


def slugify_name(value: str) -> str:
    """ASCII slug that keeps accented names readable (Türkiye -> turkiye)."""
    ascii_value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug or "destination"
