"""Module 30 - Cancellations and Refund Rules"""
import pytest
import requests
import os
import uuid
from tests.conftest import BASE_URL, skip_if_readonly, unique, auth_headers

_created_refund_rule_id = None


def test_cancellations_list(headers):
    resp = requests.get(f"{BASE_URL}/cancellations", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_cancellations_list_has_total(headers):
    resp = requests.get(f"{BASE_URL}/cancellations", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Should have some indicator of total or items
    has_total = "total" in body or "count" in body or isinstance(body, list) or "data" in body
    assert has_total, f"Expected total/items in cancellations response: {body}"


def test_cancellations_filter_pending(headers):
    resp = requests.get(
        f"{BASE_URL}/cancellations",
        headers=headers,
        params={"status": "pending"},
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list, got: {type(items)}"
    for item in items:
        status = item.get("status") or item.get("cancellation_status")
        assert status == "pending", f"Non-pending item in pending filter: {item}"


def test_cancellations_filter_approved(headers):
    resp = requests.get(
        f"{BASE_URL}/cancellations",
        headers=headers,
        params={"status": "approved"},
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), resp.text


def test_approve_nonexistent_cancellation(headers):
    resp = requests.patch(
        f"{BASE_URL}/cancellations/999999/approve",
        headers=headers,
        json={},
        timeout=10,
    )
    assert resp.status_code == 404, (
        f"Expected 404 for non-existent cancellation, got {resp.status_code}: {resp.text}"
    )


def test_reject_nonexistent_cancellation(headers):
    resp = requests.patch(
        f"{BASE_URL}/cancellations/999999/reject",
        headers=headers,
        json={"reason": "test rejection", "admin_notes": "rejected"},
        timeout=10,
    )
    assert resp.status_code in (404, 422), (
        f"Expected 404 or 422 for non-existent cancellation, got {resp.status_code}: {resp.text}"
    )


def test_refund_rules_list(headers):
    resp = requests.get(f"{BASE_URL}/refund-rules", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_refund_rules_is_list(headers):
    resp = requests.get(f"{BASE_URL}/refund-rules", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list of refund rules, got: {type(items)}"


@skip_if_readonly()
def test_create_refund_rule(headers):
    global _created_refund_rule_id
    payload = {
        "days_before_tour_min": 7,
        "days_before_tour_max": 30,
        "refund_percentage": 75,
        "description": "75% refund if cancelled 7-30 days before tour",
    }
    resp = requests.post(f"{BASE_URL}/refund-rules", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    rule = body.get("data", body)
    _created_refund_rule_id = rule.get("id")
    assert _created_refund_rule_id, f"No id in response: {body}"


def test_delete_nonexistent_refund_rule(headers):
    resp = requests.delete(
        f"{BASE_URL}/refund-rules/999999",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code == 404, (
        f"Expected 404 for non-existent refund rule, got {resp.status_code}: {resp.text}"
    )


@skip_if_readonly()
def test_delete_created_refund_rule(headers):
    if not _created_refund_rule_id:
        pytest.skip("No refund rule created to delete")
    resp = requests.delete(
        f"{BASE_URL}/refund-rules/{_created_refund_rule_id}",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code in (200, 204), resp.text
