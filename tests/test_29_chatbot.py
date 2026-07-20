"""Module 29 - Chatbot FAQ CRUD and Chat"""
import pytest
import requests
import os
import uuid
from tests.conftest import BASE_URL, skip_if_readonly, unique, auth_headers

_created_faq_id = None


def test_public_faqs_returns_200():
    resp = requests.get(f"{BASE_URL}/chatbot/faqs", timeout=10)
    assert resp.status_code == 200, resp.text


def test_public_faqs_is_list():
    resp = requests.get(f"{BASE_URL}/chatbot/faqs", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list of FAQs, got: {type(items)}"


def test_admin_faqs_requires_auth():
    resp = requests.get(f"{BASE_URL}/chatbot/admin/faqs", timeout=10)
    assert resp.status_code in (401, 403), (
        f"Expected 401/403 without auth, got {resp.status_code}: {resp.text}"
    )


def test_admin_faqs_with_auth(headers):
    resp = requests.get(f"{BASE_URL}/chatbot/admin/faqs", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list of admin FAQs, got: {type(items)}"


@skip_if_readonly()
def test_create_faq(headers):
    global _created_faq_id
    payload = {
        "question": unique("What is the cancellation policy"),
        "answer": "You can cancel within 24 hours for a full refund.",
        "category": "general",
    }
    resp = requests.post(f"{BASE_URL}/chatbot/admin/faqs", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    faq = body.get("data", body)
    _created_faq_id = faq.get("id")
    assert _created_faq_id, f"No id in response: {body}"
    assert faq.get("question") or faq.get("question_text"), f"No question in response: {body}"
    assert faq.get("answer") or faq.get("answer_text"), f"No answer in response: {body}"


@skip_if_readonly()
def test_create_faq_missing_question(headers):
    payload = {"answer": "Some answer without a question"}
    resp = requests.post(f"{BASE_URL}/chatbot/admin/faqs", headers=headers, json=payload, timeout=10)
    assert resp.status_code == 422, (
        f"Expected 422 for missing question, got {resp.status_code}: {resp.text}"
    )


@skip_if_readonly()
def test_update_faq(headers):
    if not _created_faq_id:
        pytest.skip("No FAQ created to update")
    payload = {
        "question": unique("Updated cancellation policy question"),
        "answer": "Updated answer: cancel 48 hours before for a full refund.",
    }
    resp = requests.put(
        f"{BASE_URL}/chatbot/admin/faqs/{_created_faq_id}",
        headers=headers,
        json=payload,
        timeout=10,
    )
    assert resp.status_code in (200, 201, 204), resp.text


@skip_if_readonly()
def test_delete_faq(headers):
    if not _created_faq_id:
        pytest.skip("No FAQ created to delete")
    resp = requests.delete(
        f"{BASE_URL}/chatbot/admin/faqs/{_created_faq_id}",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code in (200, 204), resp.text


def test_chatbot_chat_happy_path():
    payload = {"message": "Hello"}
    resp = requests.post(f"{BASE_URL}/chatbot/chat", json=payload, timeout=30)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Response should have a reply or message key
    reply = body.get("reply") or body.get("message") or body.get("response") or body.get("data", {})
    if isinstance(reply, dict):
        reply = reply.get("reply") or reply.get("message") or reply.get("response")
    assert reply, f"Expected a reply in chatbot response, got: {body}"


def test_chatbot_chat_greeting_response():
    payload = {"message": "Hi, what tours do you offer?"}
    resp = requests.post(f"{BASE_URL}/chatbot/chat", json=payload, timeout=30)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    reply = body.get("reply") or body.get("message") or body.get("response")
    if isinstance(reply, dict):
        reply = reply.get("reply") or reply.get("message") or reply.get("response")
    assert isinstance(reply, str) and len(reply) > 0, (
        f"Expected non-empty string reply from chatbot, got: {body}"
    )


def test_chatbot_chat_empty_message_returns_error():
    payload = {"message": ""}
    resp = requests.post(f"{BASE_URL}/chatbot/chat", json=payload, timeout=10)
    assert resp.status_code in (400, 422), (
        f"Expected 400/422 for empty message, got {resp.status_code}: {resp.text}"
    )


def test_chatbot_chat_missing_message_field_returns_422():
    payload = {}
    resp = requests.post(f"{BASE_URL}/chatbot/chat", json=payload, timeout=10)
    assert resp.status_code == 422, (
        f"Expected 422 for missing message field, got {resp.status_code}: {resp.text}"
    )
