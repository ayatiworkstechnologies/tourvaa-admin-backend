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

        def __init__(self, key, data):
            self.key = key
            self.data = data
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
