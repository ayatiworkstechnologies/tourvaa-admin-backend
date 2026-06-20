import requests
from conftest import BASE_URL


def test_invoices_list(headers):
    resp = requests.get(f"{BASE_URL}/invoices", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()
