from types import SimpleNamespace

from app.services.messaging import _serialize_booking_message


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
