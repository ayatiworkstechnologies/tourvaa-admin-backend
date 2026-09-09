"""Shared Redis client helpers - lazy-connect, graceful-degrade-to-None on
any failure so every caller works with zero Redis configured (single
instance) and self-heals if Redis is unreachable (multi-instance/worker).

get_redis_sync() backs the IP rate limiter (app/utils/ratelimit.py) and the
scheduler sweep lock (app/utils/distributed_lock.py) - both are one-shot,
occasional calls, consistent with this codebase's existing style of doing
blocking one-shot calls directly in request/loop handlers (see
app/routers/messaging.py's _ws_user, which already does a blocking sync DB
query inside an async handler).

get_redis_async() backs the /ws/messages cross-worker pub/sub
(app/services/messaging_ws.py), which needs a long-lived, non-blocking
subscriber loop.
"""
import logging

logger = logging.getLogger(__name__)

_redis_sync = None
_redis_async = None


def get_redis_sync():
    global _redis_sync
    if _redis_sync is not None:
        return _redis_sync
    try:
        from app.config import settings
        if not settings.REDIS_URL:
            return None
        import redis as redis_lib
        _redis_sync = redis_lib.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        _redis_sync.ping()
        logger.info("Redis (sync): connected at %s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning("Redis (sync): unavailable (%s), falling back to in-process state", exc)
        _redis_sync = None
    return _redis_sync


async def get_redis_async():
    global _redis_async
    if _redis_async is not None:
        return _redis_async
    try:
        from app.config import settings
        if not settings.REDIS_URL:
            return None
        import redis.asyncio as redis_async_lib
        client = redis_async_lib.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        await client.ping()
        _redis_async = client
        logger.info("Redis (async): connected at %s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning("Redis (async): unavailable (%s), falling back to single-worker delivery", exc)
        _redis_async = None
    return _redis_async
