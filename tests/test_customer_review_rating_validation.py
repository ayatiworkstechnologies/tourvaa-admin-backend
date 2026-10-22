import pytest
from pydantic import ValidationError

from app.schemas.website_cms import ReviewPayload


def _review(rating: int) -> ReviewPayload:
    return ReviewPayload(
        reviewer_name="Aishwarya",
        rating=rating,
        review_text="A well organised and memorable trip.",
    )


@pytest.mark.parametrize("rating", [1, 3, 5])
def test_customer_review_accepts_only_ratings_in_the_five_star_scale(rating: int):
    assert _review(rating).rating == rating


@pytest.mark.parametrize("rating", [0, 6])
def test_customer_review_rejects_ratings_outside_the_five_star_scale(rating: int):
    with pytest.raises(ValidationError):
        _review(rating)
