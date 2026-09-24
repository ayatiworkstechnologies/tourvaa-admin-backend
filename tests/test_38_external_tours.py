"""Day Tours & Experiences (Viator affiliate inventory).

Unit tests (no network): client error normalisation + retry/backoff, mapper,
campaign/URL rules, request validation.
Live-server tests (like the rest of this suite): public endpoints, admin RBAC,
click tracking (write test), and that Tourvaa's own tour search is untouched.
"""
from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest
import requests

from app.integrations.external_tours.constants import (
    build_campaign,
    is_allowed_external_url,
    slugify_name,
    with_campaign,
)
from app.integrations.viator import client as client_module
from app.integrations.viator.client import PRODUCTION_BASE_URL, SANDBOX_BASE_URL, ViatorClient, base_url_for
from app.integrations.viator.exceptions import (
    ViatorAccessDenied,
    ViatorAuthError,
    ViatorBadRequest,
    ViatorNotConfigured,
    ViatorNotFound,
    ViatorRateLimited,
    ViatorUnavailable,
)
from app.integrations.viator.mapper import format_duration, normalize_product
from app.integrations.viator.schemas import ExternalClickRequest, ExternalTourSearchRequest
from tests.conftest import BASE_URL, auth_headers, get_admin_token, skip_if_readonly

VIATOR_URL = "https://www.viator.com/tours/Dubai/Desert-Safari/d828-123P1?mcid=42383&pid=P00000001&medium=api&api_version=2.0"


# --- client -------------------------------------------------------------------

@pytest.fixture
def fake_viator(monkeypatch):
    """Route ViatorClient through a scripted MockTransport; record sleeps."""
    state = {"responses": [], "calls": [], "sleeps": []}

    def handler(request: httpx.Request):
        state["calls"].append(request)
        nxt = state["responses"].pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    real_client = httpx.Client
    monkeypatch.setattr(client_module.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(client_module.time, "sleep", lambda s: state["sleeps"].append(s))
    return state


def _client():
    return ViatorClient("secret-key-123", SANDBOX_BASE_URL, timeout=1)


def test_base_url_selection():
    assert base_url_for("sandbox") == SANDBOX_BASE_URL
    assert base_url_for("production") == PRODUCTION_BASE_URL
    assert base_url_for("anything-else") == SANDBOX_BASE_URL
    assert base_url_for("production", "https://example.test/partner/") == "https://example.test/partner"


def test_missing_key_is_not_configured():
    with pytest.raises(ViatorNotConfigured):
        ViatorClient("", SANDBOX_BASE_URL)


def test_headers_are_server_side_and_versioned(fake_viator):
    fake_viator["responses"] = [httpx.Response(200, json={"products": []})]
    _client().search_products({"filtering": {"destination": "828"}})
    req = fake_viator["calls"][0]
    assert req.headers["exp-api-key"] == "secret-key-123"
    assert req.headers["Accept"] == "application/json;version=2.0"
    assert req.headers["Accept-Language"] == "en-US"
    assert str(req.url) == f"{SANDBOX_BASE_URL}/products/search"


@pytest.mark.parametrize(
    "status, exc",
    [(400, ViatorBadRequest), (401, ViatorAuthError), (403, ViatorAccessDenied), (404, ViatorNotFound), (500, ViatorUnavailable)],
)
def test_non_retryable_errors_are_normalised(fake_viator, status, exc):
    fake_viator["responses"] = [httpx.Response(status, json={"code": "X", "message": "nope", "trackingId": "T1"})]
    with pytest.raises(exc) as info:
        _client().get_destinations()
    assert len(fake_viator["calls"]) == 1  # no retry
    assert "secret-key-123" not in str(info.value) and "secret-key-123" not in info.value.public_message
    assert info.value.tracking_id == "T1"


def test_429_respects_retry_after_then_succeeds(fake_viator):
    fake_viator["responses"] = [
        httpx.Response(429, headers={"Retry-After": "2"}, json={}),
        httpx.Response(200, json={"destinations": []}),
    ]
    assert _client().get_destinations() == {"destinations": []}
    assert fake_viator["sleeps"] == [2.0]


def test_429_retries_are_bounded(fake_viator):
    fake_viator["responses"] = [httpx.Response(429, json={}) for _ in range(5)]
    with pytest.raises(ViatorRateLimited):
        _client().get_destinations()
    assert len(fake_viator["calls"]) == 3  # 1 + MAX_RETRIES, never infinite
    assert all(s <= 10 for s in fake_viator["sleeps"])


def test_503_then_success(fake_viator):
    fake_viator["responses"] = [httpx.Response(503, text="down"), httpx.Response(200, json={"ok": True})]
    assert _client().get_destinations() == {"ok": True}


def test_timeout_and_network_errors_become_unavailable(fake_viator):
    fake_viator["responses"] = [httpx.ReadTimeout("slow"), httpx.ConnectError("down"), httpx.ReadTimeout("slow")]
    with pytest.raises(ViatorUnavailable):
        _client().get_destinations()
    assert len(fake_viator["calls"]) == 3


# --- helpers / mapper ---------------------------------------------------------

def test_campaign_naming():
    assert build_campaign("tourvaa", "destination") == "tourvaa-destination"
    assert build_campaign("tourvaa", "free-day") == "tourvaa-free-day"
    assert build_campaign("tourvaa", "something-else") == "tourvaa-day-tours"
    assert build_campaign("tourvaa", "home", is_agent=True) == "tourvaa-agent"


def test_affiliate_url_is_preserved_and_only_campaign_added():
    out = with_campaign(VIATOR_URL, "tourvaa-home")
    assert out.startswith(VIATOR_URL)  # nothing removed or reordered
    assert out.endswith("&campaign=tourvaa-home")
    already = VIATOR_URL + "&campaign=partner-own"
    assert with_campaign(already, "tourvaa-home") == already


@pytest.mark.parametrize(
    "url, ok",
    [
        (VIATOR_URL, True),
        ("https://shop.live.rc.viator.com/tours/x?pid=1", True),
        ("http://www.viator.com/tours/x", False),
        ("https://viator.com.evil.test/x", False),
        ("https://evil.test/?u=viator.com", False),
        ("javascript:alert(1)", False),
        (None, False),
    ],
)
def test_external_url_allow_list(url, ok):
    assert is_allowed_external_url(url) is ok


def test_slugs():
    assert slugify_name("Türkiye") == "turkiye"
    assert slugify_name("Abu Dhabi") == "abu-dhabi"


@pytest.mark.parametrize(
    "duration, label",
    [
        ({"fixedDurationInMinutes": 30}, "30 minutes"),
        ({"fixedDurationInMinutes": 90}, "1 hour 30 minutes"),
        ({"fixedDurationInMinutes": 300}, "5 hours"),
        ({"fixedDurationInMinutes": 2880}, "2 days"),
        ({"variableDurationFromMinutes": 120, "variableDurationToMinutes": 180}, "2 to 3 hours"),
        ({"unstructuredDuration": "Flexible"}, "Flexible"),
        ({}, None),
        (None, None),
    ],
)
def test_duration_labels(duration, label):
    assert format_duration(duration) == label


def test_normalize_product_uses_viator_values_only():
    raw = {
        "productCode": "123P1",
        "title": "Desert Safari",
        "description": "word " * 100,
        "productUrl": VIATOR_URL,
        "images": [{"isCover": True, "variants": [{"url": "https://img/s.jpg", "width": 200}, {"url": "https://img/m.jpg", "width": 720}, {"url": "https://img/l.jpg", "width": 1200}]}],
        "reviews": {"combinedAverageRating": 4.83, "totalReviews": 1200},
        "pricing": {"currency": "USD", "summary": {"fromPrice": 45}},
        "duration": {"fixedDurationInMinutes": 360},
        "flags": ["FREE_CANCELLATION"],
        "destinations": [{"ref": "828", "primary": True}],
    }
    item = normalize_product(raw, campaign="tourvaa-day-tours", destination_names={"828": "Dubai"})
    assert item["source"] == "VIATOR" and item["booking_type"] == "AFFILIATE_REDIRECT"
    assert item["from_price"] == 45.0 and item["currency"] == "USD"  # no Tourvaa markup
    assert item["rating"] == 4.8 and item["review_count"] == 1200
    assert item["image"] == "https://img/m.jpg"
    assert item["free_cancellation"] is True
    assert item["destination"] == {"provider_destination_id": "828", "name": "Dubai"}
    assert item["external_url"] == VIATOR_URL + "&campaign=tourvaa-day-tours"
    assert len(item["short_description"]) <= 221


def test_normalize_product_does_not_invent_values():
    item = normalize_product({"productCode": "1P", "title": "T", "productUrl": VIATOR_URL}, campaign="c")
    assert item["rating"] is None and item["review_count"] is None
    assert item["from_price"] is None and item["free_cancellation"] is None and item["image"] is None


def test_normalize_product_drops_unsafe_links():
    assert normalize_product({"productCode": "1P", "title": "T", "productUrl": "https://evil.test/x"}, campaign="c") is None


# --- validation -------------------------------------------------------------

def test_search_request_validation():
    with pytest.raises(ValueError):
        ExternalTourSearchRequest()  # no destination
    with pytest.raises(ValueError):
        ExternalTourSearchRequest(destination="dubai", provider="KLOOK")
    with pytest.raises(ValueError):
        ExternalTourSearchRequest(destination="dubai", min_price=100, max_price=10)
    with pytest.raises(ValueError):
        ExternalTourSearchRequest(destination="dubai", page_size=500)
    req = ExternalTourSearchRequest(destination="dubai", currency="xyz", source="unknown", start_date=date.today() - timedelta(days=3))
    assert req.currency == "USD" and req.source == "day-tours" and req.start_date == date.today()


def test_click_request_validation():
    with pytest.raises(ValueError):
        ExternalClickRequest(product_code="bad code!", external_url=VIATOR_URL)


# --- live server ------------------------------------------------------------

PUBLIC = f"{BASE_URL}/public/external-tours"


def _viator_live() -> bool:
    try:
        return requests.get(f"{PUBLIC}/config", timeout=10).json()["data"]["enabled"]
    except Exception:
        return False


def test_public_config_never_leaks_credentials():
    body = requests.get(f"{PUBLIC}/config", timeout=10).text.lower()
    assert "api_key" not in body and "exp-api-key" not in body and "secret" not in body


def test_categories_endpoint():
    items = requests.get(f"{PUBLIC}/categories", timeout=10).json()["items"]
    assert {"id": 21911, "name": "Food & Drink"} in items


def test_unknown_destination_is_404():
    r = requests.get(f"{PUBLIC}/destinations/definitely-not-a-place-xyz", timeout=10)
    assert r.status_code == 404 and r.json()["message"]


def test_search_rejects_invalid_request():
    assert requests.post(f"{PUBLIC}/search", json={}, timeout=10).status_code == 422
    assert requests.post(f"{PUBLIC}/search", json={"destination": "dubai", "provider": "KLOOK"}, timeout=10).status_code == 422


@pytest.mark.skipif(not _viator_live(), reason="Viator not enabled on this server")
def test_live_search_returns_normalised_affiliate_items():
    r = requests.post(f"{PUBLIC}/search", json={"destination": "dubai", "page_size": 3, "source": "home"}, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["destination"]["slug"] == "dubai" and body["total"] > 0
    for item in body["items"]:
        assert item["booking_type"] == "AFFILIATE_REDIRECT"
        assert is_allowed_external_url(item["external_url"])
        assert "pid=" in item["external_url"] and item["external_url"].endswith("campaign=tourvaa-home")
        assert "productCode" not in item  # raw Viator objects are never passed through


def test_click_rejects_non_viator_url():
    r = requests.post(f"{PUBLIC}/click", json={"product_code": "X1", "external_url": "https://evil.test/?pid=1"}, timeout=10)
    assert r.status_code == 400


@skip_if_readonly()
def test_click_is_recorded_not_booked():
    token = get_admin_token()
    before = requests.get(f"{BASE_URL}/bookings", headers=auth_headers(token), params={"limit": 1}, timeout=15).json().get("total")
    r = requests.post(f"{PUBLIC}/click", json={"product_code": "123P1", "external_url": VIATOR_URL, "source_page": "destination", "provider_destination_id": "828"}, timeout=10)
    assert r.status_code == 200 and r.json()["data"]["id"]
    after = requests.get(f"{BASE_URL}/bookings", headers=auth_headers(token), params={"limit": 1}, timeout=15).json().get("total")
    assert before == after  # a click never creates a Tourvaa booking


def test_admin_endpoints_require_auth():
    for method, path in [("get", "/viator/status"), ("post", "/viator/sync-destinations"), ("get", "/viator/mappings")]:
        r = getattr(requests, method)(f"{BASE_URL}/integrations/external-tours{path}", timeout=10)
        assert r.status_code == 401


def test_admin_status_masks_credentials():
    token = get_admin_token()
    r = requests.get(f"{BASE_URL}/integrations/external-tours/viator/status", headers=auth_headers(token), timeout=15)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["public_category"] == "Day Tours & Experiences"
    if data["api_key_configured"]:
        assert data["api_key_masked"].startswith("••••••••") and len(data["api_key_masked"]) <= 12


def test_internal_tour_search_unchanged():
    r = requests.get(f"{BASE_URL}/public/tours", params={"limit": 5}, timeout=15)
    assert r.status_code == 200
    for tour in r.json()["items"]:
        assert "booking_type" not in tour and "external_url" not in tour


def test_sandbox_links_point_customers_at_the_live_site():
    from app.integrations.external_tours.constants import to_live_site

    product = "https://shop.live.rc.viator.com/tours/Dubai/Jet-Ski/d828-5564721P1?mcid=42383&pid=P00000001&medium=api&api_version=2.0"
    assert to_live_site(product) == product.replace("shop.live.rc.viator.com", "www.viator.com")
    dest = "https://shop.live.rc.viator.com/x/d4474-ttd?mcid=42383&pid=P00000001&medium=api"
    assert to_live_site(dest, "Abu Dhabi") == "https://www.viator.com/Abu-Dhabi/d4474-ttd?mcid=42383&pid=P00000001&medium=api"
    assert to_live_site(VIATOR_URL) == VIATOR_URL  # production links untouched


def test_destination_link_matches_viator_day_trips_format():
    from app.integrations.viator.service import day_trips_url

    assert day_trips_url("723", "India", "P00244931", "search-form") == (
        "https://www.viator.com/India-tours/Day-Trips-and-Excursions/d723-g5?pid=P00244931&mcid=42383&medium=link&campaign=search-form"
    )
    assert day_trips_url("743", "United Arab Emirates", "P1", "tourvaa-home").startswith(
        "https://www.viator.com/United-Arab-Emirates-tours/Day-Trips-and-Excursions/d743-g5?pid=P1&"
    )
