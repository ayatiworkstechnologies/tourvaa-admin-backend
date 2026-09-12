"""Public tour SEO routes and backwards compatibility."""

import requests

from tests.conftest import BASE_URL


def _first_public_tour():
    response = requests.get(f"{BASE_URL}/public/tours", params={"limit": 1}, timeout=10)
    assert response.status_code == 200, response.text
    items = response.json().get("items", [])
    return items[0] if items else None


def test_public_tour_list_exposes_canonical_path():
    tour = _first_public_tour()
    if not tour:
        return
    assert tour["country_slug"]
    assert tour["slug"]
    assert tour["canonical_path"] == f'/tours/{tour["country_slug"]}/{tour["slug"]}'


def test_public_tour_canonical_route_resolves():
    tour = _first_public_tour()
    if not tour:
        return
    response = requests.get(
        f'{BASE_URL}/public/tours/{tour["country_slug"]}/{tour["slug"]}',
        timeout=10,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["id"] == tour["id"]


def test_public_tour_numeric_route_remains_compatible():
    tour = _first_public_tour()
    if not tour:
        return
    response = requests.get(f'{BASE_URL}/public/tours/{tour["id"]}', timeout=10)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["canonical_path"] == tour["canonical_path"]


def test_public_tour_detail_exposes_complete_editor_contract():
    """Every Create Tour section must survive the API boundary, including
    empty optional collections, so the frontend never has to invent data."""
    tour = _first_public_tour()
    if not tour:
        return
    response = requests.get(f'{BASE_URL}/public/tours/{tour["id"]}', timeout=10)
    assert response.status_code == 200, response.text
    detail = response.json()["data"]

    scalar_fields = {
        "title", "short_description", "long_description", "country_name",
        "city_name", "category_name", "start_location", "finish_location",
        "number_of_days", "number_of_nights", "max_group_size",
        "min_booking_size", "tour_language", "suitable_age_range",
        "pricing_type", "price_start_per_person", "currency", "banner_image",
        "map_image", "mobile_cover_image", "tour_video_url", "brochure_pdf", "seo_title",
        "seo_description", "seo_keywords", "focus_keyword", "canonical_url",
        "open_graph_image", "search_visibility", "booking_deposit",
        "deposit_type", "deposit_percentage", "deposit_cutoff_days",
        "balance_payment_deadline_days",
    }
    collection_fields = {
        "itineraries", "highlights", "inclusions", "exclusions", "gallery",
        "pricing", "calendar", "accommodations", "optional_activities",
        "extensions", "similar_tours", "discounts", "cancellation_policy",
    }
    assert scalar_fields <= detail.keys()
    assert collection_fields <= detail.keys()
    assert all(isinstance(detail[field], list) for field in collection_fields)


def test_public_tour_rejects_wrong_country_slug():
    tour = _first_public_tour()
    if not tour:
        return
    response = requests.get(
        f'{BASE_URL}/public/tours/not-the-country/{tour["slug"]}',
        timeout=10,
    )
    assert response.status_code == 404
