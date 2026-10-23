import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import bookings, messaging
from app.services.messaging import (
    _booking_message_email,
    _booking_message_url,
    _support_message_email,
    _support_message_url,
    _serialize_conversation,
    _serialize_booking_conversation,
    _serialize_booking_message,
    _serialize_message,
)


def test_booking_message_email_offers_a_secure_reply_without_booking_data(monkeypatch):
    monkeypatch.setattr(messaging.settings, "FRONTEND_URL", "https://tourvaa.example/")

    customer_url = _booking_message_url(booking_id=43, recipient_role="customer")
    admin_url = _booking_message_url(booking_id=43, recipient_role="admin")
    html = _booking_message_email(
        sender_label="Tourvaa Admin",
        message_url=customer_url,
        body="Please review the updated departure time.",
    )

    assert customer_url == "https://tourvaa.example/customer/bookings/43#booking-messages"
    assert admin_url == "https://tourvaa.example/admin/bookings/43?tab=communications#booking-messages"
    assert "View message &amp; reply" in html
    assert customer_url in html
    assert "Please review the updated departure time." in html
    assert "Booking, traveller, and payment details are not included" in html
    assert "reply securely without signing in" in html


def test_booking_message_email_escapes_chat_content():
    html = _booking_message_email(
        sender_label="Tourvaa Admin",
        message_url="https://tourvaa.example/message-reply?token=test",
        body="<script>alert('unsafe')</script>",
    )

    assert "&lt;script&gt;alert(&#x27;unsafe&#x27;)&lt;/script&gt;" in html
    assert "<script>" not in html


def test_message_email_templates_support_the_signed_reply_flow():
    from app.services.email_templates import DEFAULT_EMAIL_TEMPLATES

    templates = {template["key"]: template for template in DEFAULT_EMAIL_TEMPLATES}
    for key in ("support_message_received", "booking_message_received"):
        assert "{{message_body}}" in templates[key]["body"]
        assert "{{sender_name}}" in templates[key]["subject"]


def test_support_message_email_links_to_the_correct_secure_inbox(monkeypatch):
    monkeypatch.setattr(messaging.settings, "FRONTEND_URL", "https://tourvaa.example/")

    admin_url = _support_message_url(conversation_id=17, recipient_role="admin", participant_type="customer")
    customer_url = _support_message_url(conversation_id=17, recipient_role="customer", participant_type="customer")
    supplier_url = _support_message_url(conversation_id=17, recipient_role="supplier", participant_type="supplier")
    affiliate_url = _support_message_url(conversation_id=17, recipient_role="affiliate", participant_type="affiliate")
    html = _support_message_email(sender_label="Customer portal", message_url=admin_url, body="Please review")

    assert admin_url == "https://tourvaa.example/admin/messages?type=customer&conversation=17"
    assert customer_url == "https://tourvaa.example/customer/support"
    assert supplier_url == "https://tourvaa.example/supplier/messages"
    assert affiliate_url == "https://tourvaa.example/affiliate/messages"
    assert "View message &amp; reply" in html
    assert "https://tourvaa.example/admin/messages?type=customer&amp;conversation=17" in html
    assert "reply securely without signing in" in html
    assert "Please review" in html


def test_portal_support_message_emails_configured_admins(monkeypatch):
    conversation = SimpleNamespace(id=17, participant_type="agent", participant_user_id=9, admin_unread_count=0)
    email_alerts = []

    class Db:
        def add(self, _row):
            pass

        def commit(self):
            pass

        def refresh(self, _row):
            pass

    async def notify_ws(_event, participant_user_id):
        assert participant_user_id == 9

    monkeypatch.setattr(messaging, "get_or_create_conversation", lambda *_args: conversation)
    monkeypatch.setattr(messaging, "_participant_profile", lambda *_args: {"name": "Agent Name"})
    monkeypatch.setattr(messaging, "notify_admins", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(messaging, "_email_support_message_admins", lambda *args, **kwargs: email_alerts.append(kwargs))
    monkeypatch.setattr(messaging, "Message", lambda **values: SimpleNamespace(**values, id=31))
    monkeypatch.setattr(messaging, "_serialize_message", lambda row: {"id": row.id})
    monkeypatch.setattr(messaging, "_serialize_conversation", lambda *_args: {"id": 17})
    monkeypatch.setattr(messaging.ws_manager, "notify_new_message", notify_ws)

    asyncio.run(messaging.send_message_as_participant(Db(), SimpleNamespace(id=9), "Please help"))

    assert conversation.admin_unread_count == 1
    assert email_alerts == [{"participant_type": "agent", "conversation_id": 17}]


def test_admin_support_reply_emails_the_portal_user(monkeypatch):
    conversation = SimpleNamespace(id=17, participant_type="supplier", participant_user_id=8, participant_unread_count=0)
    email_alerts = []

    class Query:
        def filter(self, *_args):
            return self

        def first(self):
            return conversation

    class Db:
        def query(self, _model):
            return Query()

        def add(self, _row):
            pass

        def commit(self):
            pass

        def refresh(self, _row):
            pass

    async def notify_ws(_event, participant_user_id):
        assert participant_user_id == 8

    monkeypatch.setattr(messaging, "enqueue_notification", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(messaging, "_email_support_message_recipient", lambda *args, **kwargs: email_alerts.append({"user_id": args[1], **kwargs}))
    monkeypatch.setattr(messaging, "Message", lambda **values: SimpleNamespace(**values, id=32))
    monkeypatch.setattr(messaging, "_serialize_message", lambda row: {"id": row.id})
    monkeypatch.setattr(messaging, "_serialize_conversation", lambda *_args: {"id": 17})
    monkeypatch.setattr(messaging.ws_manager, "notify_new_message", notify_ws)

    asyncio.run(messaging.send_message_as_admin(Db(), 17, SimpleNamespace(id=1), "We are reviewing this"))

    assert conversation.participant_unread_count == 1
    assert email_alerts == [{"user_id": 8, "participant_type": "supplier", "conversation_id": 17, "body": "We are reviewing this"}]


def test_support_message_serializer_does_not_require_booking_recipient_role():
    """Admin-support messages are not booking messages and have no recipient role."""
    message = SimpleNamespace(
        id=9,
        conversation_id=17,
        sender_role="agent",
        sender_user_id=4,
        sender=SimpleNamespace(name="Agent Name"),
        body="Need help",
        is_deleted=False,
        created_at=None,
    )

    serialized = _serialize_message(message)

    assert serialized["sender_name"] == "Agent Name"
    assert "recipient_role" not in serialized


def test_support_conversation_serializes_both_presence_states(monkeypatch):
    conversation = SimpleNamespace(
        id=5,
        participant_type="affiliate",
        participant_user_id=12,
        participant_user=SimpleNamespace(),
        status="open",
        last_message_at=None,
        last_message_preview=None,
        admin_unread_count=0,
        participant_unread_count=0,
        created_at=None,
    )
    monkeypatch.setattr(messaging, "_participant_profile", lambda *_args: {"name": "Affiliate", "email": "affiliate@example.com"})
    monkeypatch.setattr(messaging.ws_manager, "is_user_online", lambda user_id: user_id == 12)
    monkeypatch.setattr(messaging.ws_manager, "is_admin_online", lambda: False)

    serialized = _serialize_conversation(SimpleNamespace(), conversation)

    assert serialized["participant_online"] is True
    assert serialized["admin_online"] is False


def test_booking_message_serializer_keeps_admin_reply_recipient_role():
    message = SimpleNamespace(
        id=9,
        conversation_id=17,
        sender_role="admin",
        sender_user_id=1,
        sender=SimpleNamespace(name="Tourvaa Admin"),
        recipient_role="supplier",
        body="Reply for the supplier column",
        is_deleted=False,
        created_at=None,
    )

    serialized = _serialize_booking_message(message)

    assert serialized["recipient_role"] == "supplier"
    assert serialized["body"] == "Reply for the supplier column"


def test_customer_or_agent_booking_message_stays_in_portal_conversation(monkeypatch):
    """Portal messages are shown in the Admin portal-message columns only.

    They must not be duplicated into the legacy internal communication log.
    """
    conversation = SimpleNamespace(
        id=17,
        booking_id=42,
        initiator_role="agent",
        initiator_user_id=9,
        supplier_user_id=12,
        supplier_unread_count=0,
        booking=SimpleNamespace(booking_code="TVAA-42", tour_name="Test tour"),
        initiator_user=SimpleNamespace(name="Agent Name"),
        supplier_user=SimpleNamespace(name="Supplier Name"),
        status="open",
        last_message_at=None,
        last_message_preview=None,
        initiator_unread_count=0,
        created_at=None,
    )
    added = []
    notifications = []

    class Db:
        def add(self, row):
            added.append(row)

        def commit(self):
            pass

        def refresh(self, _row):
            pass

    async def notify_ws(_event, participant_user_id):
        pass

    monkeypatch.setattr(messaging, "get_or_create_booking_conversation", lambda _db, _booking_id, _actor: conversation)
    monkeypatch.setattr(messaging, "enqueue_notification", lambda _db, **payload: notifications.append(payload))
    monkeypatch.setattr(messaging, "_email_booking_message_recipient", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(messaging.ws_manager, "notify_new_message", notify_ws)
    monkeypatch.setattr(messaging, "BookingMessage", lambda **values: SimpleNamespace(**values, id=23, sender=None, is_deleted=False, created_at=None))
    asyncio.run(messaging.send_booking_message_as_initiator(Db(), 42, SimpleNamespace(id=9), "Is the tour confirmed?"))

    assert len(added) == 1
    assert getattr(added[0], "conversation_id", None) == 17
    assert not any(getattr(row, "message_type", None) == "portal_message" for row in added)
    assert notifications[0]["user_id"] == 12
    assert added[0].recipient_role == "supplier"


def test_supplier_booking_response_hides_agent_and_customer_admin_messages(monkeypatch):
    """The Admin audit log must not turn into a supplier-visible inbox."""
    monkeypatch.setattr(bookings, "supplier_booking_value", lambda _booking: None)
    booking = SimpleNamespace(supplier_base_amount=None)
    data = {
        "communications": [
            {"id": 1, "sender_type": "agent", "visibility": "internal"},
            {"id": 2, "sender_type": "customer", "visibility": "internal"},
            {"id": 3, "sender_type": "supplier", "visibility": "internal"},
            {"id": 4, "sender_type": "admin", "visibility": "supplier"},
            {"id": 5, "sender_type": "admin", "visibility": "internal"},
        ]
    }

    filtered = bookings._supplier_safe(data, booking)

    assert [row["id"] for row in filtered["communications"]] == [3, 4]


def test_direct_booking_thread_contains_both_participant_messages():
    """Initiator and supplier see the same direct booking history."""
    def message(message_id, sender_role, recipient_role=None):
        return SimpleNamespace(
            id=message_id,
            conversation_id=17,
            sender_role=sender_role,
            sender_user_id=message_id,
            sender=SimpleNamespace(name=sender_role.title()),
            recipient_role=recipient_role,
            body=f"{sender_role} message",
            is_deleted=False,
            created_at=None,
        )

    conversation = SimpleNamespace(
        id=17,
        booking_id=42,
        booking=SimpleNamespace(booking_code="TVAA-42", tour_name="Test tour"),
        initiator_role="agent",
        initiator_user_id=7,
        initiator_user=SimpleNamespace(name="Agent Name"),
        supplier_user_id=8,
        supplier_user=SimpleNamespace(name="Supplier Name"),
        status="open",
        last_message_at=None,
        last_message_preview=None,
        initiator_unread_count=0,
        supplier_unread_count=0,
        created_at=None,
        messages=[
            message(1, "agent"),
            message(2, "supplier"),
            message(3, "admin", "agent"),
            message(4, "admin", "supplier"),
        ],
    )

    serialized = _serialize_booking_conversation(conversation, with_messages=True)

    assert [row["id"] for row in serialized["messages"]] == [1, 2, 3, 4]
    assert serialized["supplier_name"] == "Supplier Name"


def test_supplier_booking_message_is_delivered_to_booking_initiator(monkeypatch):
    """Supplier replies go directly to the booking initiator, not Admin."""
    conversation = SimpleNamespace(
        id=17,
        booking_id=42,
        initiator_role="agent",
        initiator_user_id=7,
        supplier_user_id=8,
        booking=SimpleNamespace(booking_code="TVAA-42", tour_name="Test tour"),
        initiator_user=SimpleNamespace(name="Agent Name"),
        supplier_user=SimpleNamespace(name="Supplier Name"),
        status="open",
        last_message_at=None,
        last_message_preview=None,
        initiator_unread_count=0,
        supplier_unread_count=0,
        created_at=None,
    )
    notifications = []
    websocket_recipients = []

    class Db:
        def add(self, _row):
            pass

        def commit(self):
            pass

        def refresh(self, _row):
            pass

    async def notify_ws(_event, participant_user_id):
        websocket_recipients.append(participant_user_id)

    monkeypatch.setattr(messaging, "_get_booking_conversation_for_supplier", lambda _db, _conversation_id, _user: conversation)
    monkeypatch.setattr(messaging, "enqueue_notification", lambda _db, **payload: notifications.append(payload))
    monkeypatch.setattr(messaging, "_email_booking_message_recipient", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(messaging.ws_manager, "notify_new_message", notify_ws)
    monkeypatch.setattr(messaging, "BookingMessage", lambda **values: SimpleNamespace(**values, id=24, sender=None, is_deleted=False, created_at=None))

    asyncio.run(messaging.send_booking_message_as_supplier(Db(), 17, SimpleNamespace(id=8), "Need help with this booking"))

    assert notifications[0]["user_id"] == 7
    assert websocket_recipients == [7]
    assert conversation.initiator_unread_count == 1


def test_admin_booking_reply_is_rejected_for_direct_participant_thread():
    with pytest.raises(HTTPException) as error:
        asyncio.run(messaging.send_booking_message_as_admin(None, 17, SimpleNamespace(id=1), "Please review", "supplier"))
    assert error.value.status_code == 403
