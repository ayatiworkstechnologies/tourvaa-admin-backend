"""Module 42 - Reviews (/api/customer/reviews, /api/admin/reviews, public tour reviews)

No dedicated test file existed for this module (see project audit, Trust ->
Reviews and ratings row). Covers the two server-side rules confirmed by
direct code read in app/services/reviews.py: a review can only be submitted
for a `completed` booking, and only one review per booking (also enforced by
a DB unique constraint on tour_reviews.booking_id) - plus the moderation
visibility rule that a pending/rejected review never appears on the public
tour page until an admin approves it.
"""
import uuid

import pytest
import requests

from tests.conftest import BASE_URL, create_active_account, login_with_retry, skip_if_readonly, unique, unique_phone


@pytest.fixture(scope="module")
def first_tour_id():
    # The shared session-scoped conftest fixture of the same name returns
    # any tour (admin-listing order), which may not be published - the
    # public-visibility test below needs a tour GET /public/tours/{id} can
    # actually serve, so this file sources its own the same way
    # test_38_public_tour_seo.py does.
    resp = requests.get(f"{BASE_URL}/public/tours", params={"limit": 1}, timeout=10)
    assert resp.status_code == 200, resp.text
    items = resp.json().get("items", [])
    assert items, "No published tour available to run reviews tests against"
    return items[0]["id"]


def _create_booking(customer_id: int, tour_id: int, booking_status: str = "completed") -> int:
    import app.main  # noqa: F401 - ensures every model is registered before mapper configuration
    from app.database import SessionLocal
    from app.models.bookings import Booking

    db = SessionLocal()
    try:
        booking = Booking(
            booking_code=f"TST-{uuid.uuid4().hex[:10].upper()}",
            customer_id=customer_id,
            tour_id=tour_id,
            booking_status=booking_status,
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking.id
    finally:
        db.close()


def _register_and_login_customer():
    email = f"{unique('review_cust')}@example.com"
    password = "Cust@1234"
    user = create_active_account("customer", "CUSTOMER", "Review Test Customer", email, unique_phone(), password)
    login = login_with_retry(email, password)
    assert login.status_code == 200, login.text
    token = login.json().get("data", {}).get("access_token")
    assert token, login.text
    return {"Authorization": f"Bearer {token}"}, user


@pytest.fixture(scope="module")
def customer_ctx():
    headers, user = _register_and_login_customer()

    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.models.customers import Customer

    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.user_id == user.id).first()
        customer_id = customer.id
    finally:
        db.close()

    return {"headers": headers, "customer_id": customer_id}


@pytest.fixture()
def completed_booking_id(customer_ctx, first_tour_id):
    return _create_booking(customer_ctx["customer_id"], first_tour_id, booking_status="completed")


@pytest.fixture()
def pending_booking_id(customer_ctx, first_tour_id):
    return _create_booking(customer_ctx["customer_id"], first_tour_id, booking_status="pending_payment")


def test_review_requires_auth():
    resp = requests.post(f"{BASE_URL}/customer/reviews", json={"booking_id": 1, "rating": 5}, timeout=10)
    assert resp.status_code in (401, 403)


@skip_if_readonly()
def test_review_submission_succeeds_for_completed_booking(customer_ctx, completed_booking_id):
    resp = requests.post(
        f"{BASE_URL}/customer/reviews",
        headers=customer_ctx["headers"],
        json={"booking_id": completed_booking_id, "rating": 5, "review_text": "Great trip!"},
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json().get("data", {})
    assert data.get("status") == "pending", "New reviews must start pending moderation, not auto-approved"
    assert data.get("rating") == 5


@skip_if_readonly()
def test_review_submission_rejected_for_non_completed_booking(customer_ctx, pending_booking_id):
    resp = requests.post(
        f"{BASE_URL}/customer/reviews",
        headers=customer_ctx["headers"],
        json={"booking_id": pending_booking_id, "rating": 4},
        timeout=10,
    )
    assert resp.status_code == 400, resp.text


@skip_if_readonly()
def test_duplicate_review_for_same_booking_rejected(customer_ctx, completed_booking_id):
    first = requests.post(
        f"{BASE_URL}/customer/reviews",
        headers=customer_ctx["headers"],
        json={"booking_id": completed_booking_id, "rating": 5},
        timeout=10,
    )
    assert first.status_code == 200, first.text

    second = requests.post(
        f"{BASE_URL}/customer/reviews",
        headers=customer_ctx["headers"],
        json={"booking_id": completed_booking_id, "rating": 3},
        timeout=10,
    )
    assert second.status_code == 400, second.text


@skip_if_readonly()
def test_review_rejected_for_someone_elses_booking(first_tour_id):
    other_headers, other_user = _register_and_login_customer()
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.models.customers import Customer

    db = SessionLocal()
    try:
        other_customer = db.query(Customer).filter(Customer.user_id == other_user.id).first()
        other_customer_id = other_customer.id
    finally:
        db.close()

    booking_id = _create_booking(other_customer_id, first_tour_id, booking_status="completed")

    intruder_headers, _ = _register_and_login_customer()
    resp = requests.post(
        f"{BASE_URL}/customer/reviews",
        headers=intruder_headers,
        json={"booking_id": booking_id, "rating": 5},
        timeout=10,
    )
    assert resp.status_code == 403, resp.text


def test_review_rating_out_of_range_rejected(customer_ctx, completed_booking_id):
    resp = requests.post(
        f"{BASE_URL}/customer/reviews",
        headers=customer_ctx["headers"],
        json={"booking_id": completed_booking_id, "rating": 6},
        timeout=10,
    )
    assert resp.status_code == 422, resp.text


def test_admin_reviews_list_requires_permission():
    resp = requests.get(f"{BASE_URL}/admin/reviews", timeout=10)
    assert resp.status_code in (401, 403)


def test_admin_reviews_list_loads(headers):
    resp = requests.get(f"{BASE_URL}/admin/reviews", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body or "data" in body


@skip_if_readonly()
def test_pending_review_hidden_from_public_tour_page_until_approved(headers, customer_ctx, completed_booking_id, first_tour_id):
    submit = requests.post(
        f"{BASE_URL}/customer/reviews",
        headers=customer_ctx["headers"],
        json={"booking_id": completed_booking_id, "rating": 5, "review_text": "Pending review marker"},
        timeout=10,
    )
    assert submit.status_code == 200, submit.text
    review_id = submit.json()["data"]["id"]

    before = requests.get(f"{BASE_URL}/public/tours/{first_tour_id}", timeout=10)
    assert before.status_code == 200, before.text
    before_reviews = before.json().get("data", before.json()).get("reviews", [])
    assert all(r.get("id") != review_id for r in before_reviews), "Pending review must not be publicly visible"

    approve = requests.patch(f"{BASE_URL}/admin/reviews/{review_id}/approve", headers=headers, timeout=10)
    assert approve.status_code == 200, approve.text
    assert approve.json()["data"]["status"] == "approved"

    after = requests.get(f"{BASE_URL}/public/tours/{first_tour_id}", timeout=10)
    assert after.status_code == 200, after.text
    after_reviews = after.json().get("data", after.json()).get("reviews", [])
    assert any(r.get("id") == review_id for r in after_reviews), "Approved review must appear on the public tour page"


@skip_if_readonly()
def test_rejected_review_moderation(headers, customer_ctx, first_tour_id):
    booking_id = _create_booking(customer_ctx["customer_id"], first_tour_id, booking_status="completed")
    submit = requests.post(
        f"{BASE_URL}/customer/reviews",
        headers=customer_ctx["headers"],
        json={"booking_id": booking_id, "rating": 1, "review_text": "Reject me"},
        timeout=10,
    )
    assert submit.status_code == 200, submit.text
    review_id = submit.json()["data"]["id"]

    reject = requests.patch(f"{BASE_URL}/admin/reviews/{review_id}/reject", headers=headers, timeout=10)
    assert reject.status_code == 200, reject.text
    assert reject.json()["data"]["status"] == "rejected"
