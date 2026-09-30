import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.ratelimit import MemoryLimiter

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


SENSITIVE_MARKERS = ("/admin/backups", "/admin/import", "/exports/", "/auth/change-password", "/auth/2fa/")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Three buckets per client IP: credential endpoints (strictest), heavy/sensitive endpoints, everything else.

    The client IP is `request.client.host`; behind a reverse proxy run uvicorn with --proxy-headers and
    FORWARDED_ALLOW_IPS set to the proxy so it is the real address and cannot be spoofed with X-Forwarded-For.
    """

    def __init__(self, app, per_minute: int, login_per_minute: int, sensitive_per_minute: int | None = None, limiter=None):  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.per_minute = per_minute
        self.login_per_minute = login_per_minute
        self.sensitive_per_minute = sensitive_per_minute if sensitive_per_minute is not None else max(per_minute // 10, 1)
        self.limiter = limiter or MemoryLimiter()

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method == "OPTIONS" or not request.url.path.startswith("/api"):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        path = request.url.path
        if path.endswith(("/auth/login", "/auth/forgot-password", "/auth/reset-password")):
            bucket, limit = "auth", self.login_per_minute
        elif any(m in path for m in SENSITIVE_MARKERS):
            bucket, limit = "sensitive", self.sensitive_per_minute
        else:
            bucket, limit = "api", self.per_minute
        if not await self.limiter.allow(f"{bucket}:{ip}", limit):
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests. Please slow down.", "details": None}},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
