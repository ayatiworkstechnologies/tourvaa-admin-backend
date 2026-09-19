from starlette.routing import Match

from app.routers.public import router


def test_deposit_options_is_not_shadowed_by_the_country_tour_slug_route():
    # Regression: GET /tours/{country_slug}/{tour_slug} was registered before
    # /tours/{tour_id}/deposit-options and swallowed every deposit-options call.
    prefix = router.prefix
    scope = {"type": "http", "path": f"{prefix}/tours/1/deposit-options", "method": "GET", "root_path": ""}
    first = next(route for route in router.routes if route.matches(scope)[0] == Match.FULL)
    assert first.path.endswith("/tours/{tour_id}/deposit-options"), first.path
