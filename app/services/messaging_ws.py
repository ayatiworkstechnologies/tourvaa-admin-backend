import json
import logging
import secrets
import time
from collections import defaultdict

from fastapi import WebSocket

from app.utils.redis_client import get_redis_async, get_redis_sync

logger = logging.getLogger(__name__)

TICKET_TTL_SECONDS = 30
WS_PUBSUB_CHANNEL = "ws:messages"


class _TicketStore:
    """Short-lived, single-use tickets for authenticating the /ws/messages
    handshake. The browser opens that socket directly against the backend's
    public origin (bypassing the Next.js rewrite proxy, which doesn't
    reliably support WebSocket upgrades) - a cross-origin connection can't
    rely on the httpOnly session cookie, and the frontend never has the raw
    JWT to pass as a query param. A REST call the browser already makes
    same-origin (through the proxy) mints a ticket; the WS handshake then
    redeems it once.

    Backed by Redis (SETEX + GETDEL) when configured, since a ticket minted
    by one worker's REST call must be redeemable against a different
    worker's WS handshake. Falls back to this same in-process dict when
    Redis is unavailable - correct for a single worker/instance."""

    def __init__(self):
        self._tickets: dict[str, tuple[int, float]] = {}

    def issue(self, user_id: int) -> str:
        ticket = secrets.token_urlsafe(32)
        r = get_redis_sync()
        if r is not None:
            try:
                r.setex(f"wsticket:{ticket}", TICKET_TTL_SECONDS, user_id)
                return ticket
            except Exception as exc:
                logger.warning("WS ticket store: Redis error on issue (%s), falling back to in-process", exc)
        self._sweep()
        self._tickets[ticket] = (user_id, time.monotonic() + TICKET_TTL_SECONDS)
        return ticket

    def redeem(self, ticket: str) -> int | None:
        r = get_redis_sync()
        if r is not None:
            try:
                value = r.getdel(f"wsticket:{ticket}")
                return int(value) if value is not None else None
            except Exception as exc:
                logger.warning("WS ticket store: Redis error on redeem (%s), falling back to in-process", exc)
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

    async def _deliver_locally(self, event: dict, participant_user_id: int):
        """Delivers to sockets held by *this* worker only. Called both for a
        message created on this worker and, via start_redis_subscriber, for
        one relayed from another worker/instance."""
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

    async def notify_new_message(self, event: dict, participant_user_id: int):
        await self._deliver_locally(event, participant_user_id)
        redis = await get_redis_async()
        if redis is not None:
            try:
                await redis.publish(WS_PUBSUB_CHANNEL, json.dumps({"event": event, "participant_user_id": participant_user_id}))
            except Exception as exc:
                logger.warning("WS pub/sub: publish failed (%s) - other workers won't see this message", exc)


ws_manager = MessagingConnectionManager()


async def start_redis_subscriber():
    """Relays messages published by other workers/instances to sockets held
    locally by this one. A no-op when Redis isn't configured - a single
    worker/instance already sees every message via notify_new_message's own
    direct _deliver_locally call, so nothing is lost."""
    redis = await get_redis_async()
    if redis is None:
        return
    pubsub = redis.pubsub()
    await pubsub.subscribe(WS_PUBSUB_CHANNEL)
    logger.info("WS pub/sub: subscribed to %s", WS_PUBSUB_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                payload = json.loads(message["data"])
                await ws_manager._deliver_locally(payload["event"], payload["participant_user_id"])
            except Exception:
                logger.exception("WS pub/sub: failed to relay message")
    finally:
        await pubsub.unsubscribe(WS_PUBSUB_CHANNEL)
