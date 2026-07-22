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


def test_public_tour_rejects_wrong_country_slug():
    tour = _first_public_tour()
    if not tour:
        return
    response = requests.get(
        f'{BASE_URL}/public/tours/not-the-country/{tour["slug"]}',
        timeout=10,
    )
    assert response.status_code == 404
