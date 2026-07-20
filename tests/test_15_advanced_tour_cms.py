"""Module 15 - Advanced Tour CMS (Overview / Itinerary / Inclusions / Exclusions / Highlights / Similar / Extensions / Gallery)"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique


# ── Overview ────────────────────────────────────────────────────────────────

def test_tour_overview_get(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/overview", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_tour_overview_invalid_tour(headers):
    resp = requests.get(f"{BASE_URL}/tours/9999999/overview", headers=headers, timeout=10)
    assert resp.status_code == 404


@skip_if_readonly()
def test_tour_overview_save(headers, first_tour_id):
    payload = {
        "duration_text": "3 days 2 nights",
        "start_location": "Dubai Airport",
        "end_location": "Dubai Mall",
        "group_size": "2-15",
        "tour_type": "group",
        "physical_rating": "easy",
    }
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/overview", headers=headers,
                         json=payload, timeout=10)
    assert resp.status_code in (200, 201)


@skip_if_readonly()
def test_tour_overview_invalid_rating(headers, first_tour_id):
    payload = {"physical_rating": "extreme"}
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/overview", headers=headers,
                         json=payload, timeout=10)
    assert resp.status_code in (400, 422)


# ── Itinerary ────────────────────────────────────────────────────────────────

def test_tour_itineraries_get(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/itineraries", headers=headers, timeout=10)
    assert resp.status_code == 200


_ITINERARY_ID = None


@skip_if_readonly()
def test_create_itinerary(headers, first_tour_id):
    global _ITINERARY_ID
    payload = {"day_number": 1, "day_title": unique("Day 1"), "location_name": "Dubai"}
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/itineraries", headers=headers,
                         json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    item = body.get("data", body)
    _ITINERARY_ID = item.get("id")


@skip_if_readonly()
def test_update_itinerary(headers, first_tour_id):
    if not _ITINERARY_ID:
        pytest.skip("No itinerary created")
    resp = requests.put(f"{BASE_URL}/tours/{first_tour_id}/itineraries/{_ITINERARY_ID}",
                        headers=headers, json={"day_number": 1, "day_title": unique("Updated Day"), "location_name": "Dubai"}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_reorder_itineraries(headers, first_tour_id):
    if not _ITINERARY_ID:
        pytest.skip("No itinerary created")
    resp = requests.patch(f"{BASE_URL}/tours/{first_tour_id}/itineraries/reorder",
                          headers=headers, json={"ordered_ids": [_ITINERARY_ID]}, timeout=10)
    assert resp.status_code in (200, 204)


@skip_if_readonly()
def test_delete_itinerary(headers, first_tour_id):
    if not _ITINERARY_ID:
        pytest.skip("No itinerary created")
    resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/itineraries/{_ITINERARY_ID}",
                           headers=headers, timeout=10)
    assert resp.status_code in (200, 204)


# ── Inclusions ───────────────────────────────────────────────────────────────

def test_inclusions_get(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/inclusions", headers=headers, timeout=10)
    assert resp.status_code == 200


_INCLUSION_ID = None


@skip_if_readonly()
def test_create_inclusion(headers, first_tour_id):
    global _INCLUSION_ID
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/inclusions", headers=headers,
                         json={"title": unique("Include"), "icon": "check"}, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    item = body.get("data", body)
    _INCLUSION_ID = item.get("id")


@skip_if_readonly()
def test_update_inclusion(headers, first_tour_id):
    if not _INCLUSION_ID:
        pytest.skip("No inclusion created")
    resp = requests.put(f"{BASE_URL}/tours/{first_tour_id}/inclusions/{_INCLUSION_ID}",
                        headers=headers, json={"title": unique("Updated Include")}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_delete_inclusion(headers, first_tour_id):
    if not _INCLUSION_ID:
        pytest.skip("No inclusion created")
    resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/inclusions/{_INCLUSION_ID}",
                           headers=headers, timeout=10)
    assert resp.status_code in (200, 204)


# ── Exclusions ───────────────────────────────────────────────────────────────

def test_exclusions_get(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/exclusions", headers=headers, timeout=10)
    assert resp.status_code == 200


# ── Highlights ───────────────────────────────────────────────────────────────

def test_highlights_get(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/highlights", headers=headers, timeout=10)
    assert resp.status_code == 200


# ── Similar Tours ─────────────────────────────────────────────────────────────

def test_similar_tours_get(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/similar-tours", headers=headers, timeout=10)
    assert resp.status_code == 200


@skip_if_readonly()
def test_similar_tour_cannot_be_same_tour(headers, first_tour_id):
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/similar-tours", headers=headers,
                         json={"similar_tour_id": first_tour_id}, timeout=10)
    assert resp.status_code in (400, 409, 422)


# ── Extensions ───────────────────────────────────────────────────────────────

def test_extensions_get(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/extensions", headers=headers, timeout=10)
    assert resp.status_code == 200


# ── Gallery ───────────────────────────────────────────────────────────────────

def test_gallery_get(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/gallery", headers=headers, timeout=10)
    assert resp.status_code == 200


_GALLERY_ID = None


@skip_if_readonly()
def test_create_gallery_image(headers, first_tour_id):
    global _GALLERY_ID
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/gallery", headers=headers, json={
        "image_path": "https://example.com/image.jpg",
        "image_title": unique("Gallery"),
        "image_type": "gallery",
    }, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    item = body.get("data", body)
    _GALLERY_ID = item.get("id")


@skip_if_readonly()
def test_update_gallery_image(headers, first_tour_id):
    if not _GALLERY_ID:
        pytest.skip("No gallery image created")
    resp = requests.put(f"{BASE_URL}/tours/{first_tour_id}/gallery/{_GALLERY_ID}",
                        headers=headers, json={"image_path": "https://example.com/updated.jpg", "image_title": unique("Updated Gallery"), "image_type": "gallery"}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_delete_gallery_image(headers, first_tour_id):
    if not _GALLERY_ID:
        pytest.skip("No gallery image created")
    resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/gallery/{_GALLERY_ID}",
                           headers=headers, timeout=10)
    assert resp.status_code in (200, 204)
