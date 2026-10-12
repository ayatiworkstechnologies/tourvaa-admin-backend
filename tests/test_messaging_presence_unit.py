import asyncio

from app.services import messaging_ws


class _Socket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


def test_admin_presence_is_broadcast_to_every_portal_socket():
    manager = messaging_ws.MessagingConnectionManager()
    customer_socket = _Socket()
    supplier_socket = _Socket()
    manager._user_sockets[10].add(customer_socket)
    manager._user_sockets[20].add(supplier_socket)

    event = {"type": "admin_presence", "online": True}
    asyncio.run(manager._deliver_locally(
        event,
        None,
        broadcast_participants=True,
        include_admins=False,
    ))

    assert customer_socket.events == [event]
    assert supplier_socket.events == [event]


def test_local_admin_socket_controls_initial_presence_without_redis(monkeypatch):
    manager = messaging_ws.MessagingConnectionManager()
    monkeypatch.setattr(messaging_ws, "get_redis_sync", lambda: None)

    assert manager.is_admin_online() is False
    manager._admin_sockets.add(_Socket())
    assert manager.is_admin_online() is True
