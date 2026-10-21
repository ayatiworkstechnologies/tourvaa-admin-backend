"""Unit coverage for Country Pages CMS request validation."""

import pytest
from pydantic import ValidationError
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas.website_cms import CountryPagePayload
from app.services.website_cms import get_public_destination_guide, list_public_destination_guides


def test_country_page_payload_accepts_values_at_persisted_limits():
    payload = CountryPagePayload(
        country_id=1,
        hero_title="h" * 200,
        hero_image="i" * 255,
        showcase_title="s" * 200,
        showcase_image="g" * 255,
        seo_title="t" * 200,
        seo_description="d" * 400,
    )

    assert payload.seo_description == "d" * 400


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hero_title", "h" * 201),
        ("hero_image", "i" * 256),
        ("showcase_title", "s" * 201),
        ("showcase_image", "g" * 256),
        ("seo_title", "t" * 201),
        ("seo_description", "d" * 401),
    ],
)
def test_country_page_payload_rejects_values_wider_than_database_columns(field, value):
    with pytest.raises(ValidationError):
        CountryPagePayload(country_id=1, **{field: value})


def test_public_destination_guides_only_returns_authored_country_blocks():
    rows = [
        SimpleNamespace(key="country_info_india", data={"country_name": "India", "hero_title": "India Tours"}),
        SimpleNamespace(key="country_info_empty", data={}),
        SimpleNamespace(key="country_info_invalid", data={"hero_title": "Missing country"}),
    ]
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = rows

    assert list_public_destination_guides(db) == [
        {
            "slug": "india",
            "data": {"country_name": "India", "hero_title": "India Tours"},
        }
    ]


def test_public_destination_guide_returns_only_valid_authored_data():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        data={"country_name": "India", "hero_title": "India Tours"},
    )

    assert get_public_destination_guide(db, "India") == {
        "slug": "india",
        "data": {"country_name": "India", "hero_title": "India Tours"},
    }
