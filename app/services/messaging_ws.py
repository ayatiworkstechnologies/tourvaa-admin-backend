import logging
import secrets
import time
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)

TICKET_TTL_SECONDS = 30


class _TicketStore:
    """Short-lived, single-use tickets for authenticating the /ws/messages
    handshake. The browser opens that socket directly against the backend's
    public origin (bypassing the Next.js rewrite proxy, which doesn't
    reliably support WebSocket upgrades) - a cross-origin connection can't
    rely on the httpOnly session cookie, and the frontend never has the raw
    JWT to pass as a query param. A REST call the browser already makes
    same-origin (through the proxy) mints a ticket; the WS handshake then
    redeems it once."""

    def __init__(self):
        self._tickets: dict[str, tuple[int, float]] = {}

    def issue(self, user_id: int) -> str:
        self._sweep()
        ticket = secrets.token_urlsafe(32)
        self._tickets[ticket] = (user_id, time.monotonic() + TICKET_TTL_SECONDS)
        return ticket

    def redeem(self, ticket: str) -> int | None:
        entry = self._tickets.pop(ticket, None)
        if not entry:
            return None
        user_id, expires_at = entry
        if time.monotonic() > expires_at:
            return None
        return user_id

    def _sweep(self):
        now = time.monotonic()
        expired = [key for key, (_, expires_at) in self._tickets.items() if now > expires_at]
        for key in expired:
            self._tickets.pop(key, None)


ticket_store = _TicketStore()


class MessagingConnectionManager:
    """Tracks live /ws/messages sockets so a new message can be pushed
    instantly to the admin inbox and to the sending participant's own
    portal, without polling."""

    def __init__(self):
        self._admin_sockets: set[WebSocket] = set()
        self._user_sockets: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect_admin(self, websocket: WebSocket):
        await websocket.accept()
        self._admin_sockets.add(websocket)

    async def connect_participant(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self._user_sockets[user_id].add(websocket)

    def disconnect_admin(self, websocket: WebSocket):
        self._admin_sockets.discard(websocket)

    def disconnect_participant(self, websocket: WebSocket, user_id: int):
        sockets = self._user_sockets.get(user_id)
        if sockets:
            sockets.discard(websocket)
            if not sockets:
                self._user_sockets.pop(user_id, None)

    async def notify_new_message(self, event: dict, participant_user_id: int):
        dead: list[WebSocket] = []
        for socket in self._admin_sockets:
            try:
                await socket.send_json(event)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self._admin_sockets.discard(socket)

        dead = []
        for socket in self._user_sockets.get(participant_user_id, set()):
            try:
                await socket.send_json(event)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self.disconnect_participant(socket, participant_user_id)


ws_manager = MessagingConnectionManager()
