import asyncio
import json
import logging
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import WebSocket
from jose import JWTError, jwt
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.config import settings
from app.utils.redis_client import get_redis_async, get_redis_sync

logger = logging.getLogger(__name__)

TICKET_TTL_SECONDS = 30
WS_PUBSUB_CHANNEL = "ws:messages"
PRESENCE_TTL_SECONDS = 75
SOCKET_SEND_TIMEOUT_SECONDS = 5
MAX_SOCKETS_PER_USER = 5
_PENDING_NOTIFICATION_KEY = "tourvaa_pending_ws_notifications"


def _event_envelope(event: dict) -> dict:
    """Add transport metadata while preserving the established event payload.

    The database/API remains authoritative; this envelope is only a compact
    invalidation hint and never carries a payment secret or private reason.
    """
    event.setdefault("id", secrets.token_urlsafe(16))
    event.setdefault("schema_version", "1")
    event.setdefault("occurred_at", datetime.now(timezone.utc).isoformat())
    # Keep legacy top-level fields during the staged frontend migration, but
    # every frame also has the canonical envelope data object.
    event.setdefault("data", {
        key: value for key, value in event.items()
        if key not in {"id", "type", "schema_version", "occurred_at", "data"}
    })
    return event


def queue_notification_after_commit(db: Session, user_id: int | None, notification_id: int | None) -> None:
    if user_id and notification_id:
        db.info.setdefault(_PENDING_NOTIFICATION_KEY, set()).add((int(user_id), int(notification_id)))


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
    worker's WS handshake. Without Redis, use a signed 30-second ticket so
    local reload/multi-worker development remains reliable; Redis preserves
    strict one-time redemption when it is available."""

    def __init__(self):
        self._tickets: dict[str, tuple[int, float]] = {}

    def issue(self, user_id: int) -> str:
        r = get_redis_sync()
        if r is not None:
            try:
                ticket = secrets.token_urlsafe(32)
                r.setex(f"wsticket:{ticket}", TICKET_TTL_SECONDS, user_id)
                return ticket
            except Exception as exc:
                logger.warning("WS ticket store: Redis error on issue (%s), using signed fallback", exc)
        return jwt.encode(
            {
                "sub": str(user_id),
                "purpose": "ws_ticket",
                "jti": secrets.token_urlsafe(16),
                "exp": datetime.now(timezone.utc) + timedelta(seconds=TICKET_TTL_SECONDS),
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    def redeem(self, ticket: str) -> int | None:
        r = get_redis_sync()
        if r is not None:
            try:
                value = r.getdel(f"wsticket:{ticket}")
                return int(value) if value is not None else None
            except Exception as exc:
                logger.warning("WS ticket store: Redis error on redeem (%s), trying signed fallback", exc)
        try:
            payload = jwt.decode(ticket, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            if payload.get("purpose") != "ws_ticket":
                return None
            return int(payload["sub"])
        except (JWTError, KeyError, TypeError, ValueError):
            return None

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
        # Same admin sockets, keyed by user, so one user's can be closed.
        self._admin_sockets_by_user: dict[int, set[WebSocket]] = defaultdict(set)
        self._user_sockets: dict[int, set[WebSocket]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._instance_id = secrets.token_hex(8)

    def _presence_key(self, user_id: int) -> str:
        return f"ws:presence:{user_id}:{self._instance_id}"

    def _admin_presence_key(self) -> str:
        return f"ws:admin-presence:{self._instance_id}"

    async def refresh_participant_presence(self, user_id: int):
        redis = await get_redis_async()
        if redis is not None:
            try:
                await redis.set(self._presence_key(user_id), "1", ex=PRESENCE_TTL_SECONDS)
            except Exception as exc:
                logger.warning("WS presence refresh failed (%s)", exc)

    async def refresh_admin_presence(self):
        redis = await get_redis_async()
        if redis is not None:
            try:
                await redis.set(self._admin_presence_key(), "1", ex=PRESENCE_TTL_SECONDS)
            except Exception as exc:
                logger.warning("WS admin presence refresh failed (%s)", exc)

    async def connect_admin(self, websocket: WebSocket, user_id: int):
        if len(self._admin_sockets_by_user[user_id]) >= MAX_SOCKETS_PER_USER:
            await websocket.close(code=4429)
            return False
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        self._admin_sockets.add(websocket)
        self._admin_sockets_by_user[user_id].add(websocket)
        await self.refresh_admin_presence()
        return True

    async def connect_participant(self, websocket: WebSocket, user_id: int):
        if len(self._user_sockets[user_id]) >= MAX_SOCKETS_PER_USER:
            await websocket.close(code=4429)
            return False
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        self._user_sockets[user_id].add(websocket)
        await self.refresh_participant_presence(user_id)
        return True

    def is_user_online(self, user_id: int | None) -> bool:
        """Whether this API worker currently has a live participant socket."""
        if not user_id:
            return False
        if self._user_sockets.get(user_id):
            return True
        redis = get_redis_sync()
        if redis is not None:
            try:
                return next(redis.scan_iter(match=f"ws:presence:{user_id}:*", count=10), None) is not None
            except Exception as exc:
                logger.warning("WS presence lookup failed (%s)", exc)
        return False

    def is_admin_online(self) -> bool:
        """Whether at least one messaging-enabled admin has a live socket."""
        if self._admin_sockets:
            return True
        redis = get_redis_sync()
        if redis is not None:
            try:
                return next(redis.scan_iter(match="ws:admin-presence:*", count=10), None) is not None
            except Exception as exc:
                logger.warning("WS admin presence lookup failed (%s)", exc)
        return False

    def disconnect_admin(self, websocket: WebSocket, user_id: int | None = None):
        self._admin_sockets.discard(websocket)
        for uid in ([user_id] if user_id is not None else list(self._admin_sockets_by_user)):
            sockets = self._admin_sockets_by_user.get(uid)
            if sockets:
                sockets.discard(websocket)
                if not sockets:
                    self._admin_sockets_by_user.pop(uid, None)
        if not self._admin_sockets:
            redis = get_redis_sync()
            if redis is not None:
                try:
                    redis.delete(self._admin_presence_key())
                except Exception as exc:
                    logger.warning("WS admin presence cleanup failed (%s)", exc)

    async def close_user(self, user_id: int):
        """Drop every live socket of this user held by this worker (used by
        "sign out everywhere": a socket is only authenticated when it opens,
        so without this a signed-out device kept receiving live messages)."""
        sockets = set(self._user_sockets.get(user_id, set())) | set(self._admin_sockets_by_user.get(user_id, set()))
        for socket in sockets:
            try:
                await socket.close(code=4401)
            except Exception:
                pass
            self.disconnect_participant(socket, user_id)
            self.disconnect_admin(socket, user_id)

    def request_close_user(self, user_id: int):
        """Thread-safe, fire-and-forget close_user() for sync code (e.g. a
        password change running in the threadpool). With Redis, other
        workers/instances are told too."""
        loop = self._loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.close_user(user_id), loop)
        r = get_redis_sync()
        if r is not None:
            try:
                r.publish(WS_PUBSUB_CHANNEL, json.dumps({"logout_user_id": user_id}))
            except Exception as exc:
                logger.warning("WS pub/sub: logout publish failed (%s)", exc)

    def disconnect_participant(self, websocket: WebSocket, user_id: int):
        sockets = self._user_sockets.get(user_id)
        if sockets:
            sockets.discard(websocket)
            if not sockets:
                self._user_sockets.pop(user_id, None)
                redis = get_redis_sync()
                if redis is not None:
                    try:
                        redis.delete(self._presence_key(user_id))
                    except Exception as exc:
                        logger.warning("WS presence cleanup failed (%s)", exc)

    async def notify_presence(self, user_id: int, online: bool):
        """Push participant presence to every connected admin console."""
        event = _event_envelope({"type": "participant_presence", "user_id": user_id, "online": online})
        await self._deliver_locally(event, user_id)
        redis = await get_redis_async()
        if redis is not None:
            try:
                await redis.publish(WS_PUBSUB_CHANNEL, json.dumps({"event": event, "participant_user_id": user_id}))
            except Exception as exc:
                logger.warning("WS pub/sub: presence publish failed (%s)", exc)

    async def notify_admin_presence(self, online: bool):
        """Push aggregate Tourvaa Admin availability to every portal socket."""
        event = _event_envelope({"type": "admin_presence", "online": online})
        await self._deliver_locally(
            event,
            None,
            broadcast_participants=True,
            include_admins=False,
        )
        redis = await get_redis_async()
        if redis is not None:
            try:
                await redis.publish(WS_PUBSUB_CHANNEL, json.dumps({
                    "event": event,
                    "participant_user_id": None,
                    "broadcast_participants": True,
                    "include_admins": False,
                }))
            except Exception as exc:
                logger.warning("WS pub/sub: admin presence publish failed (%s)", exc)

    async def _deliver_locally(
        self,
        event: dict,
        participant_user_id: int | None,
        *,
        broadcast_participants: bool = False,
        include_admins: bool = True,
    ):
        """Delivers to sockets held by *this* worker only. Called both for a
        message created on this worker and, via start_redis_subscriber, for
        one relayed from another worker/instance."""
        if include_admins:
            dead: list[WebSocket] = []
            for socket in self._admin_sockets:
                try:
                    await asyncio.wait_for(socket.send_json(event), timeout=SOCKET_SEND_TIMEOUT_SECONDS)
                except Exception:
                    dead.append(socket)
            for socket in dead:
                self.disconnect_admin(socket)

        user_ids = list(self._user_sockets) if broadcast_participants else ([participant_user_id] if participant_user_id is not None else [])
        for user_id in user_ids:
            dead = []
            for socket in self._user_sockets.get(user_id, set()):
                try:
                    await asyncio.wait_for(socket.send_json(event), timeout=SOCKET_SEND_TIMEOUT_SECONDS)
                except Exception:
                    dead.append(socket)
            for socket in dead:
                self.disconnect_participant(socket, user_id)

    async def notify_new_message(self, event: dict, participant_user_id: int):
        _event_envelope(event)
        await self._deliver_locally(event, participant_user_id)
        redis = await get_redis_async()
        if redis is not None:
            try:
                await redis.publish(WS_PUBSUB_CHANNEL, json.dumps({"event": event, "participant_user_id": participant_user_id}))
            except Exception as exc:
                logger.warning("WS pub/sub: publish failed (%s) - other workers won't see this message", exc)

    async def _deliver_notification_locally(self, user_id: int, event: dict) -> None:
        """Deliver an event only to the intended user's portal/admin sockets."""
        sockets = set(self._user_sockets.get(user_id, set())) | set(self._admin_sockets_by_user.get(user_id, set()))
        for socket in sockets:
            try:
                await socket.send_json(event)
            except Exception:
                self.disconnect_participant(socket, user_id)
                self.disconnect_admin(socket, user_id)

    async def notify_notification(self, user_id: int, notification_id: int) -> None:
        event = _event_envelope({"type": "new_notification", "notification_id": notification_id})
        await self._deliver_notification_locally(user_id, event)
        redis = await get_redis_async()
        if redis is not None:
            try:
                await redis.publish(WS_PUBSUB_CHANNEL, json.dumps({"notification_user_id": user_id, "event": event}))
            except Exception as exc:
                logger.warning("WS pub/sub: notification publish failed (%s)", exc)

    def request_notification(self, user_id: int | None, notification_id: int) -> None:
        """Thread-safe notification delivery for synchronous service code."""
        if not user_id:
            return
        loop = self._loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.notify_notification(user_id, notification_id), loop)
            return
        redis = get_redis_sync()
        if redis is not None:
            try:
                redis.publish(WS_PUBSUB_CHANNEL, json.dumps({"notification_user_id": user_id, "event": _event_envelope({"type": "new_notification", "notification_id": notification_id})}))
            except Exception as exc:
                logger.warning("WS pub/sub: notification publish failed (%s)", exc)

    async def notify_typing(self, event: dict, participant_user_id: int | None, *, deliver_to_participant: bool) -> None:
        """Relay an ephemeral typing state without persisting message text."""
        _event_envelope(event)
        await self._deliver_locally(event, participant_user_id if deliver_to_participant else None)
        redis = await get_redis_async()
        if redis is not None:
            try:
                await redis.publish(WS_PUBSUB_CHANNEL, json.dumps({
                    "event": event,
                    "participant_user_id": participant_user_id if deliver_to_participant else None,
                }))
            except Exception as exc:
                logger.warning("WS pub/sub: typing publish failed (%s)", exc)


ws_manager = MessagingConnectionManager()


@event.listens_for(Session, "after_commit")
def _publish_committed_notifications(session: Session) -> None:
    for user_id, notification_id in session.info.pop(_PENDING_NOTIFICATION_KEY, set()):
        ws_manager.request_notification(user_id, notification_id)


@event.listens_for(Session, "after_rollback")
def _drop_rolled_back_notifications(session: Session) -> None:
    session.info.pop(_PENDING_NOTIFICATION_KEY, None)


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
                if "logout_user_id" in payload:
                    await ws_manager.close_user(int(payload["logout_user_id"]))
                    continue
                if "notification_user_id" in payload:
                    await ws_manager._deliver_notification_locally(int(payload["notification_user_id"]), payload["event"])
                    continue
                await ws_manager._deliver_locally(
                    payload["event"],
                    payload.get("participant_user_id"),
                    broadcast_participants=bool(payload.get("broadcast_participants")),
                    include_admins=payload.get("include_admins", True),
                )
            except Exception:
                logger.exception("WS pub/sub: failed to relay message")
    finally:
        await pubsub.unsubscribe(WS_PUBSUB_CHANNEL)
