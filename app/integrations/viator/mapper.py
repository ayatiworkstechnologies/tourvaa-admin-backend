"""Viator payload -> Tourvaa's normalised external-experience shape.

Only fields Viator actually returned are filled; nothing is invented (a
missing rating stays None, not 0). The raw Viator object is never passed
through to the browser.
"""
from __future__ import annotations

from app.integrations.external_tours.constants import (
    BOOKING_AFFILIATE_REDIRECT,
    PROVIDER_VIATOR,
    PUBLIC_CATEGORY,
    is_allowed_external_url,
    to_live_site,
    with_campaign,
)

_TARGET_IMAGE_WIDTH = 720
_MAX_IMAGES = 5
_SHORT_DESCRIPTION_CHARS = 220


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _minutes_label(minutes: int) -> str:
    if minutes < 60:
        return _plural(minutes, "minute")
    if minutes % (24 * 60) == 0:
        return _plural(minutes // (24 * 60), "day")
    hours, mins = divmod(minutes, 60)
    return _plural(hours, "hour") + (f" {_plural(mins, 'minute')}" if mins else "")


def format_duration(duration: dict | None) -> str | None:
    if not isinstance(duration, dict):
        return None
    fixed = duration.get("fixedDurationInMinutes")
    if isinstance(fixed, (int, float)) and fixed > 0:
        return _minutes_label(int(fixed))
    lo, hi = duration.get("variableDurationFromMinutes"), duration.get("variableDurationToMinutes")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo > 0 and hi > 0:
        if lo == hi:
            return _minutes_label(int(lo))
        if hi < 60:
            return f"{int(lo)} to {int(hi)} minutes"
        if lo % 60 == 0 and hi % 60 == 0:
            return f"{int(lo) // 60} to {int(hi) // 60} hours"
        return f"{_minutes_label(int(lo))} to {_minutes_label(int(hi))}"
    unstructured = duration.get("unstructuredDuration")
    return unstructured.strip() if isinstance(unstructured, str) and unstructured.strip() else None


def _best_variant(image: dict) -> str | None:
    variants = [v for v in (image.get("variants") or []) if isinstance(v, dict) and v.get("url")]
    if not variants:
        return None
    # Smallest variant that is at least card-sized, else the largest one.
    wide = sorted((v for v in variants if (v.get("width") or 0) >= _TARGET_IMAGE_WIDTH), key=lambda v: v.get("width") or 0)
    chosen = wide[0] if wide else max(variants, key=lambda v: v.get("width") or 0)
    return chosen.get("url")


def _images(raw_images: list | None) -> list[str]:
    images = [img for img in (raw_images or []) if isinstance(img, dict)]
    images.sort(key=lambda img: 0 if img.get("isCover") else 1)
    urls = []
    for img in images:
        url = _best_variant(img)
        if url and url not in urls:
            urls.append(url)
        if len(urls) >= _MAX_IMAGES:
            break
    return urls


def _short_description(text: str | None) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return None
    text = " ".join(text.split())
    if len(text) <= _SHORT_DESCRIPTION_CHARS:
        return text
    cut = text[:_SHORT_DESCRIPTION_CHARS].rsplit(" ", 1)[0].rstrip(",.;:")
    return f"{cut}…"


def normalize_product(item: dict, *, campaign: str, destination_names: dict[str, str] | None = None) -> dict | None:
    """Returns None for products we can't safely show (no code/title, or no
    valid Viator affiliate URL to send the customer to)."""
    if not isinstance(item, dict):
        return None
    product_code = item.get("productCode")
    title = item.get("title")
    product_url = item.get("productUrl")
    if not product_code or not title or not is_allowed_external_url(product_url, PROVIDER_VIATOR):
        return None

    images = _images(item.get("images"))
    reviews = item.get("reviews") if isinstance(item.get("reviews"), dict) else {}
    pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
    summary = pricing.get("summary") if isinstance(pricing.get("summary"), dict) else {}
    flags = item.get("flags")

    primary = next(
        (d for d in (item.get("destinations") or []) if isinstance(d, dict) and d.get("primary")),
        next((d for d in (item.get("destinations") or []) if isinstance(d, dict)), None),
    )
    destination = None
    if primary and primary.get("ref"):
        ref = str(primary["ref"])
        destination = {"provider_destination_id": ref, "name": (destination_names or {}).get(ref)}

    rating = reviews.get("combinedAverageRating")
    review_count = reviews.get("totalReviews")
    from_price = summary.get("fromPrice")

    return {
        "id": product_code,
        "source": PROVIDER_VIATOR,
        "booking_type": BOOKING_AFFILIATE_REDIRECT,
        "provider": "Viator",
        "title": title,
        "short_description": _short_description(item.get("description")),
        "destination": destination,
        "image": images[0] if images else None,
        "images": images,
        "duration": format_duration(item.get("duration")),
        "rating": round(float(rating), 1) if isinstance(rating, (int, float)) and rating > 0 else None,
        "review_count": int(review_count) if isinstance(review_count, (int, float)) and review_count > 0 else None,
        "currency": pricing.get("currency") or None,
        # Straight from Viator - no Tourvaa markup/commission/discount/tax.
        "from_price": round(float(from_price), 2) if isinstance(from_price, (int, float)) else None,
        "free_cancellation": ("FREE_CANCELLATION" in flags) if isinstance(flags, list) else None,
        "product_code": product_code,
        # Viator's own productUrl (already carrying pid/mcid/medium), with
        # only our campaign value appended - see with_campaign.
        "external_url": with_campaign(to_live_site(product_url), campaign),
        "category": PUBLIC_CATEGORY,
    }
