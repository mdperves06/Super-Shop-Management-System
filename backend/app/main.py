import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.errors import AppError
from app.core.ratelimit import build_limiter
from app.middleware.common import RateLimitMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.utils.uploads import upload_root

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def _error(status: int, code: str, message: str, details=None, request: Request | None = None) -> JSONResponse:  # noqa: ANN001
    rid = getattr(request.state, "request_id", None) if request else None
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details, "request_id": rid}},
    )


def initialise_database() -> None:
    """Development convenience: apply migrations and reference data on start-up."""
    from alembic.config import Config

    from alembic import command
    from app.core.config import BASE_DIR
    from app.services.bootstrap import ensure_reference_data

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        ensure_reference_data(db)
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
    settings.assert_production_safe()
    if settings.auto_migrate and not settings.is_production:
        initialise_database()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Super Shop Management System REST API",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        RateLimitMiddleware, per_minute=settings.rate_limit_per_minute, login_per_minute=settings.login_rate_limit_per_minute,
        sensitive_per_minute=settings.sensitive_rate_limit_per_minute, limiter=build_limiter(settings.redis_url),
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Requested-With", "X-Token-Delivery"],
        expose_headers=["Content-Disposition", "X-Request-ID"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):  # type: ignore[no-untyped-def]
        return _error(exc.status_code, exc.code, exc.message, exc.details, request)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):  # type: ignore[no-untyped-def]
        fields = [
            {"field": ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path")), "message": e["msg"]}
            for e in exc.errors()
        ]
        first = fields[0] if fields else {"field": "", "message": "Invalid request"}
        msg = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
        return _error(422, "validation_error", msg, fields, request)

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):  # type: ignore[no-untyped-def]
        return _error(exc.status_code, "http_error", str(exc.detail), None, request)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # type: ignore[no-untyped-def]
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error(500, "internal_error", "Something went wrong on our side. Please try again.", None, request)

    @app.get("/health", tags=["health"])
    def health():  # type: ignore[no-untyped-def]
        checks: dict[str, str] = {"app": "ok"}
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:  # noqa: BLE001
            log.exception("Health check: database unreachable")
            checks["database"] = "unavailable"
        healthy = all(v == "ok" for v in checks.values())
        return JSONResponse(status_code=200 if healthy else 503, content={"status": "healthy" if healthy else "degraded", "checks": checks})

    app.include_router(api_router)
    # Only product images/logos are public (needed by <img>); attachments go through authenticated endpoints.
    media = upload_root() / "products"
    media.mkdir(parents=True, exist_ok=True)
    app.mount("/media/products", StaticFiles(directory=str(media)), name="product-media")
    return app


app = create_app()
