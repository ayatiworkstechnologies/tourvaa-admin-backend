from app.routers.public import router


def test_public_tour_pdf_routes_precede_the_canonical_country_slug_route():
    """Specific PDF paths must win over /tours/{country_slug}/{tour_slug}."""
    paths = [route.path for route in router.routes]
    canonical_index = paths.index("/tours/{country_slug}/{tour_slug}")

    assert paths.index("/tours/{tour_id}/brochure") < canonical_index
    assert paths.index("/tours/{tour_id}/itinerary") < canonical_index
