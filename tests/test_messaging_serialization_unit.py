import asyncio
from types import SimpleNamespace

from app.services import bookings, messaging
from app.services.messaging import _serialize_booking_conversation, _serialize_booking_message


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


def test_customer_or_agent_booking_message_is_logged_for_admin(monkeypatch):
    """The booking composer is an admin-support channel, so its message
    must enter the booking communication timeline with a clear sender."""
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
    monkeypatch.setattr(messaging, "notify_admins", lambda _db, **payload: notifications.append(payload))
    monkeypatch.setattr(messaging.ws_manager, "notify_new_message", notify_ws)
    monkeypatch.setattr(messaging, "BookingMessage", lambda **values: SimpleNamespace(**values, id=23, sender=None, recipient_role=None, is_deleted=False, created_at=None))
    monkeypatch.setattr(messaging, "BookingCommunication", lambda **values: SimpleNamespace(**values))

    asyncio.run(messaging.send_booking_message_as_initiator(Db(), 42, SimpleNamespace(id=9), "Is the tour confirmed?"))

    timeline_row = next(row for row in added if getattr(row, "message_type", None) == "portal_message")
    assert timeline_row.booking_id == 42
    assert timeline_row.sender_type == "agent"
    assert timeline_row.message_type == "portal_message"
    assert timeline_row.visibility == "internal"
    assert notifications[0]["title"] == "New agent booking message"


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


def test_agent_thread_excludes_admin_reply_addressed_to_supplier():
    """A shared booking row cannot leak an Admin-to-Supplier reply to Agent."""
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

    serialized = _serialize_booking_conversation(
        conversation,
        with_messages=True,
        hide_supplier_identity=True,
        viewer_role="agent",
    )

    assert [row["id"] for row in serialized["messages"]] == [1, 3]


def test_supplier_booking_message_is_delivered_to_admin_not_booking_initiator(monkeypatch):
    """Supplier booking chat is a private channel with Tourvaa Admin."""
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
    monkeypatch.setattr(messaging, "notify_admins", lambda _db, **payload: notifications.append(payload))
    monkeypatch.setattr(messaging.ws_manager, "notify_new_message", notify_ws)
    monkeypatch.setattr(messaging, "BookingMessage", lambda **values: SimpleNamespace(**values, id=24, sender=None, recipient_role=None, is_deleted=False, created_at=None))

    asyncio.run(messaging.send_booking_message_as_supplier(Db(), 17, SimpleNamespace(id=8), "Need help with this booking"))

    assert notifications[0]["title"] == "New supplier booking message"
    assert websocket_recipients == [8]
    assert conversation.initiator_unread_count == 0
