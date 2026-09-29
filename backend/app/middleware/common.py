import logging
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

log = logging.getLogger("app.request")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        start = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid
        log.info("%s %s %s %.0fms rid=%s", request.method, request.url.path, response.status_code, ms, rid)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Small in-process sliding-window limiter. Use a shared store (Redis/WAF) behind multiple workers."""

    def __init__(self, app, per_minute: int, login_per_minute: int):  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.per_minute = per_minute
        self.login_per_minute = login_per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def _allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method == "OPTIONS" or not request.url.path.startswith("/api"):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        path = request.url.path
        strict = path.endswith(("/auth/login", "/auth/forgot-password", "/auth/reset-password"))
        limit = self.login_per_minute if strict else self.per_minute
        key = f"{ip}:{'auth' if strict else 'api'}"
        if not self._allow(key, limit):
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests. Please slow down.", "details": None}},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
