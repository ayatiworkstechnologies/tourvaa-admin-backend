"""Unit coverage for Country Pages CMS request validation."""

import pytest
from pydantic import ValidationError
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas.website_cms import CountryPagePayload
from app.models.website_cms import CountryPage
from app.services.website_cms import _s_country_page, get_public_destination_guide, list_public_destination_guides


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


def test_country_page_database_constraint_prevents_duplicate_country_pages():
    """Concurrent POSTs are ultimately protected by the persisted unique FK."""
    assert CountryPage.__table__.c.country_id.unique is True


def test_country_page_serialization_uses_persisted_country_slug_not_display_name():
    page = SimpleNamespace(
        id=9, country_id=3, hero_title="Tours", hero_description=None,
        hero_image=None, showcase_title=None, showcase_description=None,
        showcase_image=None, seo_title=None, seo_description=None,
        is_active=True, created_at=None, updated_at=None,
    )
    country = SimpleNamespace(country_name="Renamed Country", slug="published-country-url")

    result = _s_country_page(page, country)

    assert result["country_name"] == "Renamed Country"
    assert result["country_slug"] == "published-country-url"
