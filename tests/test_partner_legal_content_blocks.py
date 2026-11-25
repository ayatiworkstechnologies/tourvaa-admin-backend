import pytest
from fastapi import HTTPException
from app.schemas.website_cms import ContentBlockPayload
from app.services.website_cms import get_content_block, upsert_content_block
import app.services.website_cms as cms


class FakeSession:
    def __init__(self):
        self.row = None

    def query(self, _model):
        return self

    def filter(self, _condition):
        return self

    def first(self):
        return self.row

    def add(self, row):
        self.row = row

    def commit(self):
        pass

    def refresh(self, _row):
        pass


@pytest.mark.parametrize("key", [
    f"{audience}_{policy}_{part}"
    for audience in ("partner", "supplier")
    for policy in ("terms", "privacy")
    for part in ("hero", "sections")
])
def test_partner_legal_blocks_can_be_read_and_saved(key, monkeypatch):
    class FakeBlock:
        key = "key"

        def __init__(self, key, data, version=1):
            self.key = key
            self.data = data
            self.version = 1
            self.updated_at = None

    monkeypatch.setattr(cms, "HomepageContentBlock", FakeBlock)
    db = FakeSession()
    assert get_content_block(db, key)["data"] == {}
    payload = {"items": [{"title": "Example", "body": "Text"}]}
    assert upsert_content_block(db, key, ContentBlockPayload(data=payload))["data"] == payload
    assert get_content_block(db, key)["data"] == payload


def test_unknown_content_block_remains_rejected():
    with pytest.raises(HTTPException) as error:
        get_content_block(FakeSession(), "partner_privacy_unknown")
    assert error.value.status_code == 404


def test_contact_channels_reject_invalid_contact_email():
    with pytest.raises(HTTPException) as error:
        upsert_content_block(
            FakeSession(),
            "contact_page_channels",
            ContentBlockPayload(data={"contact_email": "not-an-email"}),
        )

    assert error.value.status_code == 422
    assert error.value.detail == "Contact email must be a valid email address"


def test_contact_channels_save_contact_email_without_replacing_the_block(monkeypatch):
    class FakeBlock:
        key = "contact_page_channels"

        def __init__(self, key, data, version=1):
            self.key = key
            self.data = data
            self.version = version
            self.updated_at = None

    monkeypatch.setattr(cms, "HomepageContentBlock", FakeBlock)
    db = FakeSession()
    payload = {"heading": "Get in Touch", "contact_email": " support@example.com "}

    saved = upsert_content_block(db, "contact_page_channels", ContentBlockPayload(data=payload))

    assert saved["data"] == {"heading": "Get in Touch", "contact_email": "support@example.com"}
    assert get_content_block(db, "contact_page_channels")["data"] == saved["data"]


def test_contact_offices_accept_dynamic_unique_locations_with_coordinates():
    payload = ContentBlockPayload(data={"items": [
        {"office_id": "office-1", "location": "Wellington, New Zealand", "latitude": -41.2865, "longitude": 174.7762},
        {"office_id": "office-2", "location": "Tokyo, Japan"},
        {"office_id": "office-3", "location": "Cape Town, South Africa"},
        {"office_id": "office-4", "location": "Toronto, Canada"},
    ]})

    assert cms._validate_contact_offices(payload.data) is None


def test_contact_offices_reject_duplicate_locations_case_insensitively():
    payload = ContentBlockPayload(data={"items": [
        {"office_id": "office-1", "location": "Auckland, New Zealand"},
        {"office_id": "office-2", "location": " auckland, new zealand "},
    ]})

    with pytest.raises(HTTPException) as error:
        cms._validate_contact_offices(payload.data)

    assert error.value.status_code == 422
    assert error.value.detail == "Office names or locations must be unique"


@pytest.mark.parametrize("latitude,longitude", [(91, 0), (0, -181), ("bad", 10), (10, None)])
def test_contact_offices_reject_invalid_or_incomplete_coordinates(latitude, longitude):
    payload = ContentBlockPayload(data={"items": [
        {"office_id": "office-1", "location": "Tokyo, Japan", "latitude": latitude, "longitude": longitude},
    ]})

    with pytest.raises(HTTPException) as error:
        cms._validate_contact_offices(payload.data)

    assert error.value.status_code == 422


def test_travel_advice_categories_reject_more_than_eight_cards():
    payload = ContentBlockPayload(data={"items": [{"title": f"Card {index}"} for index in range(9)]})

    with pytest.raises(HTTPException) as error:
        upsert_content_block(FakeSession(), "travel_advice_categories", payload)

    assert error.value.status_code == 422
    assert error.value.detail == "items accepts at most 8 cards"


def test_content_block_rejects_outdated_editor_save(monkeypatch):
    class FakeBlock:
        key = "partner_terms_hero"

        def __init__(self, key, data, version=1):
            self.key = key
            self.data = data
            self.version = version
            self.updated_at = None

    monkeypatch.setattr(cms, "HomepageContentBlock", FakeBlock)
    db = FakeSession()
    db.row = FakeBlock("partner_terms_hero", {"title": "Current"}, version=3)

    with pytest.raises(HTTPException) as error:
        upsert_content_block(
            db,
            "partner_terms_hero",
            ContentBlockPayload(data={"title": "Outdated"}, expected_version=2),
        )

    assert error.value.status_code == 409
    assert db.row.data == {"title": "Current"}


def test_content_block_rejects_excessive_nesting():
    nested = "value"
    for _ in range(9):
        nested = {"child": nested}

    with pytest.raises(ValueError, match="nested"):
        ContentBlockPayload(data={"root": nested})
