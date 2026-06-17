import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/suppliers?page=1&limit=5&search=",
        "/agents?page=1&limit=5&search=",
        "/affiliates?page=1&limit=5&search=",
        "/countries?page=1&limit=5&search=",
        "/cities?page=1&limit=5&search=",
        "/tour-categories?page=1&limit=5&search=",
        "/tour-subcategories?page=1&limit=5&search=",
        "/tours?page=1&limit=5&search=",
    ],
)
def test_week_6_8_list_endpoints(api_client, path):
    payload = api_client.get(path)
    assert payload["status"] == "success"
    assert isinstance(payload["data"], list)
    assert isinstance(payload["total"], int)
    assert isinstance(payload["page"], int)
    assert isinstance(payload["limit"], int)
    assert isinstance(payload["total_pages"], int)
