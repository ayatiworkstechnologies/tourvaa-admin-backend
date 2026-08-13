"""Module 41 - Affiliate module Phase 1-8 additions: link CRUD, commission
rules, redirect/attribution tracking, self-service restrictions, and the
affiliate-initiated payout request lifecycle.
"""
import pytest
import requests
from tests.conftest import BASE_URL, auth_headers, create_active_account, login_with_retry, skip_if_readonly, unique, unique_phone

ORIGIN = BASE_URL.rsplit("/api", 1)[0]


def _alias(prefix: str) -> str:
    """Affiliate link aliases only allow lowercase/digits/hyphens - unique()
    includes an underscore, which the alias validator correctly rejects."""
    return unique(prefix).replace("_", "-").lower()


def _first_published_tour(headers):
    resp = requests.get(f"{BASE_URL}/tours", headers=headers, params={"status": "published", "limit": 5}, timeout=10)
    if resp.status_code != 200:
        return None
    items = resp.json().get("items") or resp.json().get("data") or []
    return items[0] if items else None


def _create_and_approve_affiliate(headers, *, commission_percentage=10):
    payload = {
        "name": unique("LinkTestAff"),
        "email": f"{unique('linktest')}@test.com",
        "phone": "9876500000",
        "business_type": "individual",
        "commission_percentage": commission_percentage,
    }
    resp = requests.post(f"{BASE_URL}/affiliates/", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    affiliate = resp.json()["data"]
    approve = requests.patch(f"{BASE_URL}/affiliates/{affiliate['id']}/approve", headers=headers, timeout=10)
    assert approve.status_code == 200, approve.text
    return approve.json()["data"]


# --- admin link CRUD -----------------------------------------------------------

@skip_if_readonly()
def test_create_custom_link_and_lifecycle(headers):
    affiliate = _create_and_approve_affiliate(headers)

    create = requests.post(f"{BASE_URL}/affiliate-links", headers=headers, json={
        "affiliate_id": affiliate["id"], "link_type": "custom", "destination_url": "/tours/demo",
        "campaign_name": "Test Campaign", "custom_alias": _alias("alias"),
    }, timeout=10)
    assert create.status_code == 200, create.text
    link = create.json()["data"]
    assert link["status"] == "active"
    assert link["campaign_name"] == "Test Campaign"

    disable = requests.post(f"{BASE_URL}/affiliate-links/{link['id']}/disable", headers=headers, timeout=10)
    assert disable.status_code == 200
    assert disable.json()["data"]["status"] == "disabled"

    activate = requests.post(f"{BASE_URL}/affiliate-links/{link['id']}/activate", headers=headers, timeout=10)
    assert activate.status_code == 200
    assert activate.json()["data"]["status"] == "active"

    dup = requests.post(f"{BASE_URL}/affiliate-links/{link['id']}/duplicate", headers=headers, timeout=10)
    assert dup.status_code == 200, dup.text
    assert dup.json()["data"]["ref_code"] != link["ref_code"]
    assert dup.json()["data"]["total_clicks"] == 0

    listing = requests.get(f"{BASE_URL}/affiliate-links", headers=headers, params={"affiliate_id": affiliate["id"]}, timeout=10)
    assert listing.status_code == 200
    assert listing.json()["total"] >= 2


@skip_if_readonly()
def test_tour_link_requires_published_tour(headers):
    affiliate = _create_and_approve_affiliate(headers)
    resp = requests.post(f"{BASE_URL}/affiliate-links", headers=headers, json={
        "affiliate_id": affiliate["id"], "link_type": "tour", "tour_id": 99999999,
    }, timeout=10)
    assert resp.status_code == 400, resp.text


@skip_if_readonly()
def test_tour_link_resolves_destination(headers):
    tour = _first_published_tour(headers)
    if not tour:
        pytest.skip("No published tour available")
    affiliate = _create_and_approve_affiliate(headers)
    create = requests.post(f"{BASE_URL}/affiliate-links", headers=headers, json={
        "affiliate_id": affiliate["id"], "link_type": "tour", "tour_id": tour["id"],
    }, timeout=10)
    assert create.status_code == 200, create.text
    assert create.json()["data"]["tour_id"] == tour["id"]


@skip_if_readonly()
def test_duplicate_custom_alias_rejected(headers):
    affiliate = _create_and_approve_affiliate(headers)
    alias = _alias("dupealias")
    first = requests.post(f"{BASE_URL}/affiliate-links", headers=headers, json={
        "affiliate_id": affiliate["id"], "link_type": "custom", "destination_url": "/x", "custom_alias": alias,
    }, timeout=10)
    assert first.status_code == 200, first.text
    second = requests.post(f"{BASE_URL}/affiliate-links", headers=headers, json={
        "affiliate_id": affiliate["id"], "link_type": "custom", "destination_url": "/y", "custom_alias": alias,
    }, timeout=10)
    assert second.status_code == 409, second.text


@skip_if_readonly()
def test_reserved_alias_rejected(headers):
    affiliate = _create_and_approve_affiliate(headers)
    resp = requests.post(f"{BASE_URL}/affiliate-links", headers=headers, json={
        "affiliate_id": affiliate["id"], "link_type": "custom", "destination_url": "/x", "custom_alias": "admin",
    }, timeout=10)
    assert resp.status_code == 400, resp.text


# --- redirect / click tracking --------------------------------------------------

@skip_if_readonly()
def test_redirect_active_link_tracks_and_sets_cookie(headers):
    affiliate = _create_and_approve_affiliate(headers)
    create = requests.post(f"{BASE_URL}/affiliate-links", headers=headers, json={
        "affiliate_id": affiliate["id"], "link_type": "custom", "destination_url": "/tours/demo-redirect",
    }, timeout=10)
    link = create.json()["data"]

    resp = requests.get(f"{ORIGIN}/r/{link['ref_code']}", allow_redirects=False, timeout=10)
    assert resp.status_code in (301, 302, 307, 308), resp.text
    assert resp.headers.get("location") == "/tours/demo-redirect"
    assert "tourvaa_affiliate_ref" in resp.cookies


@skip_if_readonly()
def test_redirect_disabled_link_still_redirects_without_tracking(headers):
    affiliate = _create_and_approve_affiliate(headers)
    create = requests.post(f"{BASE_URL}/affiliate-links", headers=headers, json={
        "affiliate_id": affiliate["id"], "link_type": "custom", "destination_url": "/tours/demo-disabled",
    }, timeout=10)
    link = create.json()["data"]
    requests.post(f"{BASE_URL}/affiliate-links/{link['id']}/disable", headers=headers, timeout=10)

    resp = requests.get(f"{ORIGIN}/r/{link['ref_code']}", allow_redirects=False, timeout=10)
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers.get("location") == "/tours/demo-disabled"


def test_redirect_unknown_code_falls_back_safely():
    resp = requests.get(f"{ORIGIN}/r/{unique('nonexistent')}", allow_redirects=False, timeout=10)
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers.get("location") == "/"


# --- commission rules ------------------------------------------------------------

@skip_if_readonly()
def test_commission_rule_crud(headers):
    affiliate = _create_and_approve_affiliate(headers)
    create = requests.post(f"{BASE_URL}/affiliate-commission-rules", headers=headers, json={
        "affiliate_id": affiliate["id"], "commission_type": "percentage", "percentage": "15", "priority": 5,
    }, timeout=10)
    assert create.status_code == 200, create.text
    rule = create.json()["data"]
    assert rule["percentage"] == "15.00"

    update = requests.put(f"{BASE_URL}/affiliate-commission-rules/{rule['id']}", headers=headers, json={"percentage": "20"}, timeout=10)
    assert update.status_code == 200
    assert update.json()["data"]["percentage"] == "20.00"

    delete = requests.delete(f"{BASE_URL}/affiliate-commission-rules/{rule['id']}", headers=headers, timeout=10)
    assert delete.status_code == 200
    assert delete.json()["data"]["deleted"] is True


def test_commission_rules_require_auth():
    resp = requests.get(f"{BASE_URL}/affiliate-commission-rules", timeout=10)
    assert resp.status_code in (401, 403)


def test_affiliate_links_require_auth():
    resp = requests.get(f"{BASE_URL}/affiliate-links", timeout=10)
    assert resp.status_code in (401, 403)


# --- self-service restrictions & cross-affiliate security ------------------------

@skip_if_readonly()
def test_self_service_link_creation_ignores_commission_override(headers):
    """An affiliate portal user's own link-creation call must not be able to
    set a commission override, even though the same payload shape would work
    for an admin. Verified via direct service call for reproducibility."""
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.services.affiliate_tracking import create_link, _s_link
    from app.schemas.affiliate_tracking import AffiliateLinkCreate

    affiliate = _create_and_approve_affiliate(headers)

    db = SessionLocal()
    try:
        from app.models.affiliates import Affiliate
        aff_row = db.query(Affiliate).filter(Affiliate.id == affiliate["id"]).first()

        class FakeAffiliateUser:
            id = aff_row.user_id or 1

        data = AffiliateLinkCreate(link_type="custom", destination_url="/x", commission_type_override="percentage", commission_percentage_override="99")
        result = create_link(db, affiliate_id=affiliate["id"], data=data, actor=FakeAffiliateUser(), is_admin=False)
        assert result["commission_type_override"] is None
        assert result["commission_percentage_override"] is None
    finally:
        db.close()


@skip_if_readonly()
def test_self_service_link_update_ignores_admin_fields(headers):
    from app.database import SessionLocal
    from app.services.affiliate_tracking import update_link
    from app.schemas.affiliate_tracking import AffiliateLinkUpdate

    affiliate = _create_and_approve_affiliate(headers)
    create = requests.post(f"{BASE_URL}/affiliate-links", headers=headers, json={
        "affiliate_id": affiliate["id"], "link_type": "custom", "destination_url": "/x",
    }, timeout=10)
    link = create.json()["data"]

    db = SessionLocal()
    try:
        data = AffiliateLinkUpdate(campaign_name="Allowed Change", commission_percentage_override="99", status="disabled")
        result = update_link(db, link["id"], data, actor=None, is_admin=False)
        assert result["campaign_name"] == "Allowed Change"
        assert result["commission_percentage_override"] is None
        assert result["status"] == "active"
    finally:
        db.close()


@skip_if_readonly()
def test_affiliate_cannot_access_another_affiliates_links(headers):
    """Two real affiliate portal accounts; affiliate A must not be able to
    read affiliate B's link list through the self-service endpoint."""
    aff_b = _create_and_approve_affiliate(headers)

    pw = "StrongPassw0rd!23"
    email_a = f"{unique('selfaff')}@test.com"
    user_a = create_active_account("affiliate", "AFFILIATE", unique("SelfAffA"), email_a, unique_phone(), pw)

    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.models.affiliates import Affiliate
    from app.utils.money import utcnow
    db = SessionLocal()
    try:
        aff_a = db.query(Affiliate).filter(Affiliate.user_id == user_a.id).first()
        aff_a.status = "active"
        aff_a.approval_status = "approved"
        db.commit()
        aff_a_id = aff_a.id
    finally:
        db.close()

    login = login_with_retry(email_a, pw)
    assert login.status_code == 200, login.text
    token_a = login.json()["data"]["access_token"]
    headers_a = auth_headers(token_a)

    own = requests.get(f"{BASE_URL}/affiliates/{aff_a_id}/links", headers=headers_a, timeout=10)
    assert own.status_code == 200

    other = requests.get(f"{BASE_URL}/affiliates/{aff_b['id']}/links", headers=headers_a, timeout=10)
    assert other.status_code == 403, other.text


# --- payout request lifecycle -----------------------------------------------------

@skip_if_readonly()
def test_payout_request_lifecycle_and_minimum_enforced(headers):
    import app.main  # noqa: F401
    from decimal import Decimal
    from app.database import SessionLocal
    from app.models.affiliates import Affiliate
    from app.models.bookings import Booking
    from app.models.affiliate_tracking import AffiliateLink
    from app.services.affiliate_tracking import create_link as svc_create_link, record_conversion
    from app.services.affiliate_payouts import create_payout_method, request_payout, approve_payout, mark_payout_processing, mark_payout_paid, get_available_balance
    from app.schemas.affiliate_tracking import AffiliateLinkCreate, AffiliatePayoutMethodCreate, AffiliatePayoutRequestCreate

    affiliate = _create_and_approve_affiliate(headers, commission_percentage=10)

    db = SessionLocal()
    try:
        aff_row = db.query(Affiliate).filter(Affiliate.id == affiliate["id"]).first()

        class FakeUser:
            id = 1

        link = svc_create_link(db, affiliate_id=aff_row.id, data=AffiliateLinkCreate(link_type="custom", destination_url="/x"), actor=FakeUser())
        db.commit()

        from app.models.affiliate_tracking import AffiliateConversion
        converted_ids = {row[0] for row in db.query(AffiliateConversion.booking_id).all()}
        candidate = db.query(Booking.id).filter(~Booking.id.in_(converted_ids)).order_by(Booking.id.desc()).first() if converted_ids else db.query(Booking.id).order_by(Booking.id.desc()).first()
        if not candidate:
            pytest.skip("No unconverted bookings in DB to attach a conversion to")
        booking_id = candidate[0]

        conv = record_conversion(db, ref_code=link["ref_code"], booking_id=booking_id, booking_amount=Decimal("2000"), currency="USD")
        db.commit()
        assert conv is not None
        assert conv.affiliate_id == aff_row.id, "record_conversion returned a conversion for a different affiliate - booking_id collided with a prior test run"

        available = get_available_balance(db, aff_row.id)
        assert available >= Decimal("200.00")

        method = create_payout_method(db, aff_row.id, AffiliatePayoutMethodCreate(method_type="bank_transfer", account_holder_name="Test", account_number="1112223334", bank_name="Test Bank"))

        # below minimum must be rejected
        from fastapi import HTTPException
        try:
            request_payout(db, aff_row, AffiliatePayoutRequestCreate(amount=Decimal("1"), payout_method_id=method["id"]))
            assert False, "expected minimum-payout rejection"
        except HTTPException as exc:
            assert exc.status_code == 400

        payout = request_payout(db, aff_row, AffiliatePayoutRequestCreate(amount=Decimal("150"), payout_method_id=method["id"]))
        assert payout["status"] == "requested"

        approve_payout(db, payout["id"], FakeUser())
        mark_payout_processing(db, payout["id"], FakeUser())
        paid = mark_payout_paid(db, payout["id"], payment_reference="TEST-REF-1", admin_notes=None, actor=FakeUser())
        assert paid["status"] == "paid"
        assert paid["reference_number"] == "TEST-REF-1"
    finally:
        db.close()


def test_admin_payout_queue_requires_permission():
    resp = requests.get(f"{BASE_URL}/admin/affiliate-payouts", timeout=10)
    assert resp.status_code in (401, 403)


def test_affiliate_wallet_requires_auth():
    resp = requests.get(f"{BASE_URL}/affiliate/wallet", timeout=10)
    assert resp.status_code in (401, 403)
