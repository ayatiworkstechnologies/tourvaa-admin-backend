"""
Simple in-memory IP-based rate limiter for auth endpoints.

Uses a sliding-window counter per (IP, key) pair.  Not suitable for
multi-process deployments — replace with Redis-backed throttling there.
"""
import time
import threading
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_lock = threading.Lock()
_windows: dict[str, deque] = defaultdict(deque)
_CLEANUP_INTERVAL = 300  # seconds between stale-bucket sweeps
_last_cleanup = time.monotonic()


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _cleanup_stale_buckets(now: float) -> None:
    """Remove buckets that have had no activity in the longest window (10 min)."""
    global _last_cleanup
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    stale_cutoff = now - 600
    empty_keys = [k for k, dq in _windows.items() if not dq or dq[-1] < stale_cutoff]
    for k in empty_keys:
        del _windows[k]


def check_rate_limit(request: Request, key: str, max_calls: int, window_seconds: int):
    """
    Raise 429 if `key` (typically an endpoint name) from the client IP
    has exceeded `max_calls` within the last `window_seconds`.
    """
    ip = _client_ip(request)
    bucket = f"{ip}:{key}"
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
