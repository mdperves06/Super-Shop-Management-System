"""Request rate limiting.

Per-process memory by default. Set REDIS_URL and every worker/instance shares one counter, which is what a
multi-instance deployment needs (memory counters would multiply the effective limit by the number of workers).
If Redis is unreachable the limiter degrades to the local counter instead of taking the API down.
"""

import logging
import threading
import time
from collections import defaultdict, deque

log = logging.getLogger("app.ratelimit")

WINDOW = 60


class MemoryLimiter:
    """Sliding window per key, process-local."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    async def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > WINDOW:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self.hits) > 50_000:  # keep memory bounded under scanning traffic
                for k in [k for k, v in self.hits.items() if not v or now - v[-1] > WINDOW][:10_000]:
                    self.hits.pop(k, None)
            return True


class RedisLimiter:
    """Fixed one-minute window shared across processes: SET NX EX + INCR in one MULTI block."""

    def __init__(self, url: str, client=None) -> None:  # type: ignore[no-untyped-def]
        if client is None:
            import redis.asyncio as aioredis

            client = aioredis.from_url(url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True)
        self.redis = client
        self.fallback = MemoryLimiter()
        self._warned_at = 0.0

    async def allow(self, key: str, limit: int) -> bool:
        window = int(time.time() // WINDOW)
        k = f"ssm:rl:{key}:{window}"
        try:
            pipe = self.redis.pipeline(transaction=True)
            pipe.set(k, 0, ex=WINDOW * 2, nx=True)
            pipe.incr(k)
            *_, count = await pipe.execute()
            return int(count) <= limit
        except Exception as exc:  # noqa: BLE001 - never let a cache outage block sales
            if time.monotonic() - self._warned_at > 60:
                self._warned_at = time.monotonic()
                log.warning("Redis rate limiter unavailable (%s); using the local counter", exc.__class__.__name__)
            return await self.fallback.allow(key, limit)


def build_limiter(redis_url: str | None):  # type: ignore[no-untyped-def]
    if redis_url:
        return RedisLimiter(redis_url)
    return MemoryLimiter()
