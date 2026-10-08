"""Unit coverage for Country Pages CMS request validation."""

import pytest
from pydantic import ValidationError

from app.schemas.website_cms import CountryPagePayload


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
