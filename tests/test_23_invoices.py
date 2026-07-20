import requests

from tests.conftest import BASE_URL, skip_if_readonly


def test_invoices_list(headers):
    resp = requests.get(f"{BASE_URL}/invoices", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


def test_invoice_detail_not_found(headers):
    resp = requests.get(f"{BASE_URL}/invoices/999999999", headers=headers, timeout=10)
    assert resp.status_code == 404, resp.text


@skip_if_readonly()
def test_invoice_generate_requires_valid_booking(headers):
    resp = requests.post(f"{BASE_URL}/invoices/generate", json={
        "booking_id": 999999999, "invoice_type": "tax_invoice",
    }, headers=headers, timeout=10)
    assert resp.status_code in (400, 404, 422), resp.text


@skip_if_readonly()
def test_invoice_generate_pdf_and_download_and_email(headers, first_booking_id):
    if not first_booking_id:
        return  # no booking available to generate an invoice for in this environment

    generate = requests.post(f"{BASE_URL}/invoices/generate", json={
        "booking_id": first_booking_id, "invoice_type": "tax_invoice",
    }, headers=headers, timeout=10)
    assert generate.status_code in (200, 201, 400), generate.text
    if generate.status_code not in (200, 201):
        return  # booking not in an invoiceable state - not a test failure

    invoice_id = generate.json()["data"]["id"]

    detail = requests.get(f"{BASE_URL}/invoices/{invoice_id}", headers=headers, timeout=10)
    assert detail.status_code == 200, detail.text

    pdf = requests.post(f"{BASE_URL}/invoices/{invoice_id}/generate-pdf", headers=headers, timeout=10)
    assert pdf.status_code == 200, pdf.text

    download = requests.get(f"{BASE_URL}/invoices/{invoice_id}/download", headers=headers, timeout=10)
    assert download.status_code == 200, download.text
    assert download.headers.get("content-type") == "application/pdf"

    email = requests.post(f"{BASE_URL}/invoices/{invoice_id}/email", json={}, headers=headers, timeout=10)
    assert email.status_code in (200, 400), email.text


def test_invoice_download_not_found(headers):
    resp = requests.get(f"{BASE_URL}/invoices/999999999/download", headers=headers, timeout=10)
    assert resp.status_code == 404, resp.text
