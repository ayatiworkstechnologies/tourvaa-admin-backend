"""
IP-based sliding-window rate limiter.

Uses Redis when REDIS_URL is configured — safe across multiple workers.
Falls back to an in-process deque when Redis is unavailable or not configured.
"""
import logging
import time
import threading
from collections import defaultdict, deque

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis client (optional)
# ---------------------------------------------------------------------------

_redis = None


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        from app.config import settings
        if not settings.REDIS_URL:
            return None
        import redis as redis_lib
        _redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        _redis.ping()
        logger.info("Rate limiter: using Redis at %s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning("Rate limiter: Redis unavailable (%s), falling back to in-memory", exc)
        _redis = None
    return _redis


# ---------------------------------------------------------------------------
# In-memory fallback (single-process only)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_windows: dict[str, deque] = defaultdict(deque)
_CLEANUP_INTERVAL = 300
_last_cleanup = time.monotonic()


def _cleanup_stale_buckets(now: float) -> None:
    global _last_cleanup
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    stale_cutoff = now - 600
    empty_keys = [k for k, dq in _windows.items() if not dq or dq[-1] < stale_cutoff]
    for k in empty_keys:
        del _windows[k]


def _check_in_memory(bucket: str, max_calls: int, window_seconds: int) -> None:
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        _cleanup_stale_buckets(now)
        dq = _windows[bucket]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= max_calls:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait before trying again.",
                headers={"Retry-After": str(window_seconds)},
            )
        dq.append(now)


# ---------------------------------------------------------------------------
# Redis sliding-window implementation
# ---------------------------------------------------------------------------

_LUA_SLIDING_WINDOW = """
local key     = KEYS[1]
local now     = tonumber(ARGV[1])
local window  = tonumber(ARGV[2])
local limit   = tonumber(ARGV[3])
local cutoff  = now - window

redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)
if count >= limit then
    return 0
end
redis.call('ZADD', key, now, now .. '-' .. math.random(1e9))
redis.call('EXPIRE', key, window + 1)
return 1
"""


def _check_redis(r, bucket: str, max_calls: int, window_seconds: int) -> None:
    try:
        result = r.eval(_LUA_SLIDING_WINDOW, 1, bucket, time.time(), window_seconds, max_calls)
        if not result:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait before trying again.",
                headers={"Retry-After": str(window_seconds)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Rate limiter: Redis eval failed (%s), falling back to in-memory", exc)
        _check_in_memory(bucket, max_calls, window_seconds)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request, key: str, max_calls: int, window_seconds: int):
    """
    Raise 429 if the client IP has exceeded max_calls within window_seconds.
    Uses Redis when available, in-memory deque otherwise.
    """
    ip = _client_ip(request)
    bucket = f"rl:{ip}:{key}"
    r = _get_redis()
    if r:
        _check_redis(r, bucket, max_calls, window_seconds)
    else:
        _check_in_memory(bucket, max_calls, window_seconds)
