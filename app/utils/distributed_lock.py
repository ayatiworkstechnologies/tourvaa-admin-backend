"""Distributed per-tick lock for the scheduled background sweeps in
app/main.py, so multiple workers/instances don't each independently run the
same sweep (duplicate emails/refunds/status flips).

Uses a Redis SET NX EX per tick - whichever worker's tick reaches Redis
first for a given lock name wins that interval, and the lock expires just
before the next tick so no explicit release is needed (a worker crashing
mid-sweep doesn't wedge the lock past one cycle).

When Redis isn't configured (or is unreachable), acquire_sweep_lock always
returns True - this preserves today's behavior exactly for a single-worker
deployment with no Redis at all. Running with WEB_CONCURRENCY > 1 while
Redis is unreachable would let every worker run each sweep independently
until Redis recovers - a temporary, self-healing degradation rather than a
crash, matching this codebase's existing fail-open philosophy (see
app/utils/ratelimit.py).
"""
import logging

from app.utils.redis_client import get_redis_sync

logger = logging.getLogger(__name__)


def acquire_sweep_lock(name: str, ttl_seconds: int) -> bool:
    r = get_redis_sync()
    if r is None:
        return True
    try:
        return bool(r.set(f"sweeplock:{name}", "1", nx=True, ex=ttl_seconds))
    except Exception as exc:
        logger.warning("Sweep lock %r: Redis error (%s), proceeding without lock", name, exc)
        return True
