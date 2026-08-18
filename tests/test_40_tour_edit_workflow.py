"""Module 37 - Tour Edit/Update workflow: withdraw, repricing, review
comments, and optimistic concurrency, all against a real supplier-owned
tour taken all the way to published."""
import time

import pytest
import requests

from tests.conftest import (
    BASE_URL, create_active_account, login_with_retry, skip_if_readonly,
    unique, unique_phone,
)


def _find_supplier_id_by_name(admin_headers, name):
    resp = requests.get(f"{BASE_URL}/suppliers", params={"search": name, "limit": 10}, headers=admin_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    items = resp.json().get("items", [])
    match = next((s for s in items if s.get("name") == name or s.get("supplier_name") == name), None)
    return match["id"] if match else None


@pytest.fixture(scope="module")
def supplier_ctx(headers):
    name = f"Edit Flow Supplier {unique('n')}"
    email = f"{unique('sup')}@example.com"
    password = "Supp@1234"
    create_active_account("supplier", "SUPPLIER", name, email, unique_phone(), password)

    supplier_id = _find_supplier_id_by_name(headers, name)
    assert supplier_id, f"Newly created supplier {name!r} not found via admin search"

    approve = requests.post(f"{BASE_URL}/suppliers/{supplier_id}/approve", headers=headers, timeout=10)
    assert approve.status_code == 200, approve.text

    login = login_with_retry(email, password)
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "supplier_id": supplier_id}


@pytest.fixture(scope="module")
def supplier_headers(supplier_ctx):
    return supplier_ctx["headers"]


def _create_draft_tour(headers, supplier_id, first_country_id, first_category_id):
    resp = requests.post(f"{BASE_URL}/tours", headers=headers, json={
        "title": unique("Edit Flow Tour"),
        "number_of_days": 3,
        "price_start_per_person": 199.0,
        "country_id": first_country_id,
        "category_id": first_category_id,
        "supplier_id": supplier_id,
    }, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["data"]["id"]


def _submit_and_approve(headers, tour_id):
    resp = requests.post(f"{BASE_URL}/tours/{tour_id}/submit-for-approval", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    version_id = resp.json()["data"]["id"]
    resp = requests.patch(f"{BASE_URL}/tours/{tour_id}/versions/{version_id}/approve", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    return version_id


def _publish(headers, tour_id):
    resp = requests.patch(f"{BASE_URL}/tours/{tour_id}/status", headers=headers, json={"status": "published"}, timeout=10)
    assert resp.status_code == 200, resp.text


@pytest.fixture(scope="module")
def published_tour_id(headers, supplier_ctx, first_country_id, first_category_id):
    tour_id = _create_draft_tour(headers, supplier_ctx["supplier_id"], first_country_id, first_category_id)
    _submit_and_approve(headers, tour_id)
    _publish(headers, tour_id)
    return tour_id


# ─── Published tour stays live through a content edit ─────────────────────────

@skip_if_readonly()
def test_supplier_content_edit_keeps_tour_published(headers, supplier_headers, published_tour_id):
    # Itinerary is one of the "versioned" child resources that triggers
    # maybe_resubmit_for_review on every supplier write (inclusions/
    # highlights/exclusions currently aren't wired into that path at all --
    # a separate, pre-existing gap outside this pass's scope).
    resp = requests.post(f"{BASE_URL}/tours/{published_tour_id}/itineraries", headers=supplier_headers, json={
        "day_number": 1, "day_title": unique("Day"),
    }, timeout=10)
    assert resp.status_code in (200, 201), resp.text

    detail = requests.get(f"{BASE_URL}/tours/{published_tour_id}", headers=headers, timeout=10)
    assert detail.status_code == 200, detail.text
    tour = detail.json()["data"]
    assert tour["status"] == "published", "Published tour must stay live through review, not flip to pending_approval"
    assert tour["pending_review_kind"] == "pending_approval"


@skip_if_readonly()
def test_admin_approving_content_edit_keeps_tour_published(headers, published_tour_id):
    # The versions list endpoint returns {status, items, ...} (no `data` wrap),
    # like every other list endpoint in the API.
    versions = requests.get(f"{BASE_URL}/tours/{published_tour_id}/versions", headers=headers, timeout=10).json()["items"]
    pending = next(v for v in versions if v["status"] == "pending_approval")
    resp = requests.patch(f"{BASE_URL}/tours/{published_tour_id}/versions/{pending['id']}/approve", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text

    detail = requests.get(f"{BASE_URL}/tours/{published_tour_id}", headers=headers, timeout=10).json()["data"]
    assert detail["status"] == "published", "Approving a review must not demote an already-published tour"
    assert detail["pending_review_kind"] is None


# ─── Supplier pricing change on a published tour -> repricing_required ────────

@skip_if_readonly()
def test_supplier_can_create_a_brand_new_pricing_slab(headers, supplier_headers, supplier_ctx, first_country_id, first_category_id):
    # Regression: a supplier creating a *new* slab (not editing an existing
    # one, which already has real DB-backed values) used to 500 -- a
    # freshly-constructed TourPricing row's admin_markup_type/value are
    # None until flush, and the code path that seeds them from the payload
    # only runs for admin actors, so _apply_markup crashed on float + None.
    tour_id = _create_draft_tour(headers, supplier_ctx["supplier_id"], first_country_id, first_category_id)
    resp = requests.post(f"{BASE_URL}/tours/{tour_id}/pricing", headers=supplier_headers, json={
        "passenger_from": 1, "passenger_to": 4, "adult_price": 500.0, "child_price": 250.0,
    }, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    assert "admin_markup_value" not in resp.json()["data"]


@skip_if_readonly()
def test_supplier_pricing_edit_freezes_storefront_price(headers, supplier_headers, published_tour_id):
    # Created by admin directly (not a supplier action), so it's treated as
    # an already-approved baseline price with a real storefront value --
    # exactly the "existing public price" the supplier's later edit below
    # must not silently change.
    create = requests.post(f"{BASE_URL}/tours/{published_tour_id}/pricing", headers=headers, json={
        "passenger_from": 1, "passenger_to": 4, "adult_price": 100.0, "child_price": 50.0,
    }, timeout=10)
    assert create.status_code in (200, 201), create.text
    slab = create.json()["data"]
    slab_id = slab["id"]
    frozen_storefront = slab["storefront_adult_price"]
    assert frozen_storefront is not None

    updated = requests.put(f"{BASE_URL}/tours/{published_tour_id}/pricing/{slab_id}", headers=supplier_headers, json={
        "passenger_from": 1, "passenger_to": 4, "adult_price": 999.0, "child_price": 50.0,
    }, timeout=10)
    assert updated.status_code == 200, updated.text
    supplier_view = updated.json()["data"]
    assert "storefront_adult_price" not in supplier_view, "Tourvaa's public price must never be returned to a supplier"
    assert "admin_markup_value" not in supplier_view, "Tourvaa's own markup must never be returned to a supplier"
    assert supplier_view["supplier_final_adult_price"] != frozen_storefront

    admin_view = requests.get(f"{BASE_URL}/tours/{published_tour_id}/pricing", headers=headers, timeout=10).json()["data"]
    admin_slab = next(p for p in admin_view if p["id"] == slab_id)
    assert admin_slab["storefront_adult_price"] == frozen_storefront, "Public price must not change until admin approves"

    detail = requests.get(f"{BASE_URL}/tours/{published_tour_id}", headers=headers, timeout=10).json()["data"]
    assert detail["status"] == "published"
    assert detail["pending_review_kind"] == "repricing_required"

    versions = requests.get(f"{BASE_URL}/tours/{published_tour_id}/versions", headers=headers, timeout=10).json()["items"]
    pending = next(v for v in versions if v["status"] == "pending_approval")
    approve = requests.patch(f"{BASE_URL}/tours/{published_tour_id}/versions/{pending['id']}/approve", headers=headers, timeout=10)
    assert approve.status_code == 200, approve.text

    final = requests.get(f"{BASE_URL}/tours/{published_tour_id}/pricing", headers=headers, timeout=10).json()["data"]
    final_slab = next(p for p in final if p["id"] == slab_id)
    assert final_slab["storefront_adult_price"] != frozen_storefront, "Approval must recalculate the public price"


# ─── Withdraw submission ───────────────────────────────────────────────────────

@skip_if_readonly()
def test_withdraw_returns_draft_tour_to_draft(headers, supplier_headers, supplier_ctx, first_country_id, first_category_id):
    tour_id = _create_draft_tour(headers, supplier_ctx["supplier_id"], first_country_id, first_category_id)
    submit = requests.post(f"{BASE_URL}/tours/{tour_id}/submit-for-approval", headers=supplier_headers, timeout=10)
    assert submit.status_code == 200, submit.text

    withdraw = requests.post(f"{BASE_URL}/tours/{tour_id}/withdraw", headers=supplier_headers, timeout=10)
    assert withdraw.status_code == 200, withdraw.text

    detail = requests.get(f"{BASE_URL}/tours/{tour_id}", headers=headers, timeout=10).json()["data"]
    assert detail["status"] == "draft"

    again = requests.post(f"{BASE_URL}/tours/{tour_id}/withdraw", headers=supplier_headers, timeout=10)
    assert again.status_code == 400, "Withdrawing with nothing pending should fail, not silently succeed"


# ─── Structured review comments ────────────────────────────────────────────────

@skip_if_readonly()
def test_reject_with_comments_are_visible_and_resolvable(headers, supplier_headers, supplier_ctx, first_country_id, first_category_id):
    tour_id = _create_draft_tour(headers, supplier_ctx["supplier_id"], first_country_id, first_category_id)
    submit = requests.post(f"{BASE_URL}/tours/{tour_id}/submit-for-approval", headers=headers, timeout=10)
    version_id = submit.json()["data"]["id"]

    reject = requests.patch(f"{BASE_URL}/tours/{tour_id}/versions/{version_id}/reject", headers=headers, json={
        "rejection_reason": "Needs more detail",
        "comments": [
            {"section": "itinerary", "field_name": None, "comment": "Add at least one day", "severity": "required"},
        ],
    }, timeout=10)
    assert reject.status_code == 200, reject.text

    listed = requests.get(f"{BASE_URL}/tours/{tour_id}/review-comments", headers=supplier_headers, timeout=10)
    assert listed.status_code == 200, listed.text
    comments = listed.json()["data"]
    assert len(comments) == 1
    assert comments[0]["section"] == "itinerary"
    assert comments[0]["status"] == "open"

    resolve = requests.patch(f"{BASE_URL}/tours/{tour_id}/review-comments/{comments[0]['id']}/resolve", headers=supplier_headers, timeout=10)
    assert resolve.status_code == 200, resolve.text
    assert resolve.json()["data"]["status"] == "resolved"


@skip_if_readonly()
def test_supplier_cannot_create_review_comment(headers, supplier_headers, supplier_ctx, first_country_id, first_category_id):
    tour_id = _create_draft_tour(headers, supplier_ctx["supplier_id"], first_country_id, first_category_id)
    resp = requests.post(f"{BASE_URL}/tours/{tour_id}/review-comments", headers=supplier_headers, json={
        "section": "basic", "comment": "should be blocked", "severity": "minor",
    }, timeout=10)
    assert resp.status_code == 403, resp.text


# ─── Optimistic concurrency ─────────────────────────────────────────────────────

@skip_if_readonly()
def test_stale_expected_updated_at_returns_409(headers, supplier_ctx, first_country_id, first_category_id):
    tour_id = _create_draft_tour(headers, supplier_ctx["supplier_id"], first_country_id, first_category_id)
    fetched = requests.get(f"{BASE_URL}/tours/{tour_id}", headers=headers, timeout=10).json()["data"]
    stale_updated_at = fetched["updated_at"]

    # MySQL's DateTime columns here have 1-second resolution -- without this
    # gap, first_edit's onupdate() timestamp could land in the same second
    # as stale_updated_at, making it indistinguishable from "unchanged" and
    # defeating the test.
    time.sleep(1.1)
    first_edit = requests.put(f"{BASE_URL}/tours/{tour_id}", headers=headers, json={
        "title": unique("Concurrency Edit 1"), "number_of_days": 3,
        "expected_updated_at": stale_updated_at,
    }, timeout=10)
    assert first_edit.status_code == 200, first_edit.text

    second_edit = requests.put(f"{BASE_URL}/tours/{tour_id}", headers=headers, json={
        "title": unique("Concurrency Edit 2 (stale)"), "number_of_days": 3,
        "expected_updated_at": stale_updated_at,
    }, timeout=10)
    assert second_edit.status_code == 409, second_edit.text
    # The app's HTTPException handler (middleware/error_handlers.py) returns
    # a dict `detail` payload directly as the response body, unwrapped.
    assert second_edit.json()["current_updated_by"] is not None


@skip_if_readonly()
def test_fresh_expected_updated_at_succeeds(headers, supplier_ctx, first_country_id, first_category_id):
    tour_id = _create_draft_tour(headers, supplier_ctx["supplier_id"], first_country_id, first_category_id)
    fetched = requests.get(f"{BASE_URL}/tours/{tour_id}", headers=headers, timeout=10).json()["data"]

    resp = requests.put(f"{BASE_URL}/tours/{tour_id}", headers=headers, json={
        "title": unique("Concurrency Fresh Edit"), "number_of_days": 3,
        "expected_updated_at": fetched["updated_at"],
    }, timeout=10)
    assert resp.status_code == 200, resp.text


# ─── Admin-only tour delete ────────────────────────────────────────────────────

@skip_if_readonly()
def test_supplier_cannot_delete_tour(headers, supplier_headers, supplier_ctx, first_country_id, first_category_id):
    tour_id = _create_draft_tour(headers, supplier_ctx["supplier_id"], first_country_id, first_category_id)
    resp = requests.delete(f"{BASE_URL}/tours/{tour_id}", headers=supplier_headers, timeout=10)
    assert resp.status_code == 403, resp.text

    # Confirm it's still there, untouched by the rejected attempt.
    still_there = requests.get(f"{BASE_URL}/tours/{tour_id}", headers=headers, timeout=10)
    assert still_there.status_code == 200


@skip_if_readonly()
def test_admin_can_delete_tour_without_bookings(headers, supplier_ctx, first_country_id, first_category_id):
    tour_id = _create_draft_tour(headers, supplier_ctx["supplier_id"], first_country_id, first_category_id)
    resp = requests.delete(f"{BASE_URL}/tours/{tour_id}", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text

    gone = requests.get(f"{BASE_URL}/tours/{tour_id}", headers=headers, timeout=10)
    assert gone.status_code == 404


@skip_if_readonly()
def test_admin_cannot_delete_tour_with_bookings(headers, supplier_ctx, first_country_id, first_category_id):
    tour_id = _create_draft_tour(headers, supplier_ctx["supplier_id"], first_country_id, first_category_id)
    _submit_and_approve(headers, tour_id)
    _publish(headers, tour_id)
    booking = requests.post(f"{BASE_URL}/bookings", headers=headers, json={
        "customer_id": 1, "tour_id": tour_id, "booking_source": "admin",
        "adults_count": 1, "children_count": 0,
        "tour_name": "Delete Guard Test", "tour_date": "2028-06-01",
    }, timeout=10)
    assert booking.status_code in (200, 201), booking.text

    resp = requests.delete(f"{BASE_URL}/tours/{tour_id}", headers=headers, timeout=10)
    assert resp.status_code == 400, resp.text
    assert "booking" in str(resp.json()).lower()
