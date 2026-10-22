import pytest
from pydantic import ValidationError

from app.schemas.website_cms import ReviewPayload


def _review(rating: float) -> ReviewPayload:
    return ReviewPayload(
        reviewer_name="Aishwarya",
        rating=rating,
        review_text="A well organised and memorable trip.",
    )


@pytest.mark.parametrize("rating", [1, 3, 3.5, 5])
def test_customer_review_accepts_half_star_ratings_in_the_five_star_scale(rating: float):
    assert _review(rating).rating == rating


@pytest.mark.parametrize("rating", [0, 3.25, 5.5, 6])
def test_customer_review_rejects_ratings_outside_the_half_star_scale(rating: float):
    with pytest.raises(ValidationError):
        _review(rating)
