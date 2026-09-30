from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.core.errors import AuthenticationError, NotFoundError
from app.models.auth import RefreshToken
from app.models.base import utcnow
from app.schemas.auth import (
    ChangePassword,
    ForgotPassword,
    LoginRequest,
    MeOut,
    ProfileUpdate,
    RefreshRequest,
    ResetPassword,
    TokenPair,
    TotpCode,
    TotpSetup,
    UserOut,
)
from app.schemas.common import Message, UTCDateTime
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _me(user) -> MeOut:  # type: ignore[no-untyped-def]
    base = UserOut.model_validate(user).model_dump()
    return MeOut(**base, permissions=sorted(user.permission_codes), landing_path=auth_service.landing_path(user))


COOKIE_NAME = "ssm_refresh"
COOKIE_PATH = "/api/v1/auth"


class LoginResponse(TokenPair):
    user: MeOut


def _set_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, refresh_token, max_age=settings.refresh_token_expire_days * 86400, path=COOKIE_PATH, httponly=True,
        secure=settings.refresh_cookie_secure, samesite=settings.cookie_samesite.lower(),  # type: ignore[arg-type]
        domain=settings.cookie_domain or None,
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, domain=settings.cookie_domain or None)


def _deliver(request: Request, response: Response, tokens: TokenPair) -> TokenPair:
    """Browsers get the refresh token only as an HttpOnly cookie (invisible to JavaScript / XSS).
    Non-browser API clients can opt in to the token in the body with `X-Token-Delivery: body`."""
    _set_cookie(response, tokens.refresh_token)
    if request.headers.get("x-token-delivery") != "body":
        tokens = tokens.model_copy(update={"refresh_token": ""})
    return tokens


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response, db: DB):  # noqa: ANN201
    user, tokens = auth_service.login(db, body.email, body.password, body.otp, request)
    return LoginResponse(**_deliver(request, response, tokens).model_dump(), user=_me(user))


@router.post("/refresh", response_model=TokenPair)
def refresh(request: Request, response: Response, db: DB, body: RefreshRequest | None = None):  # noqa: ANN201
    token = body.refresh_token if body else None
    if not token:
        token = request.cookies.get(COOKIE_NAME)
        # cookie-borne credentials are CSRF-able, so they must come with a header a cross-site form cannot set
        if token and request.headers.get("x-requested-with") != "ssm":
            raise AuthenticationError("Missing CSRF header", code="csrf_failed")
    if not token:
        raise AuthenticationError("Not signed in", code="not_authenticated")
    try:
        tokens = auth_service.refresh(db, token, request)
    except AuthenticationError:
        _clear_cookie(response)
        raise
    return _deliver(request, response, tokens)


@router.post("/logout", response_model=Message)
def logout(request: Request, response: Response, db: DB, user: CurrentUser):  # noqa: ANN201
    auth_service.logout(db, user, getattr(request.state, "session_id", None), request)
    _clear_cookie(response)
    return Message(message="Signed out")


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser):  # noqa: ANN201
    return _me(user)


@router.patch("/me", response_model=MeOut)
def update_me(body: ProfileUpdate, db: DB, user: CurrentUser):  # noqa: ANN201
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    return _me(user)


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePassword, request: Request, db: DB, user: CurrentUser):  # noqa: ANN201
    auth_service.change_password(db, user, body.current_password, body.new_password, request)
    return Message(message="Password changed. Please sign in again.")


@router.post("/forgot-password")
def forgot_password(body: ForgotPassword, request: Request, db: DB):  # noqa: ANN201
    token = auth_service.request_password_reset(db, body.email, request)
    out = {"message": "If that email exists, a reset link has been sent."}
    if settings.environment in ("development", "test") and token:
        out["dev_token"] = token  # never returned in production
    return out


@router.post("/reset-password", response_model=Message)
def reset_password(body: ResetPassword, request: Request, db: DB):  # noqa: ANN201
    auth_service.reset_password(db, body.token, body.new_password, request)
    return Message(message="Password updated. You can now sign in.")


@router.post("/2fa/setup", response_model=TotpSetup)
def totp_setup(db: DB, user: CurrentUser):  # noqa: ANN201
    secret, uri = auth_service.totp_setup(db, user)
    return TotpSetup(secret=secret, otpauth_uri=uri)


@router.post("/2fa/enable", response_model=Message)
def totp_enable(body: TotpCode, db: DB, user: CurrentUser):  # noqa: ANN201
    auth_service.totp_enable(db, user, body.code)
    return Message(message="Two-factor authentication enabled")


@router.post("/2fa/disable", response_model=Message)
def totp_disable(body: TotpCode, db: DB, user: CurrentUser):  # noqa: ANN201
    auth_service.totp_disable(db, user, body.code)
    return Message(message="Two-factor authentication disabled")


class SessionOut(BaseModel):
    id: int
    created_at: UTCDateTime
    ip_address: str | None
    user_agent: str | None
    current: bool


@router.get("/sessions", response_model=list[SessionOut])
def my_sessions(request: Request, db: DB, user: CurrentUser):  # noqa: ANN201
    current = getattr(request.state, "session_id", None)
    rows = db.scalars(select(RefreshToken).where(
        RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > utcnow()
    ).order_by(RefreshToken.id.desc()).limit(20))
    return [SessionOut(id=r.id, created_at=r.created_at, ip_address=r.ip_address, user_agent=r.user_agent, current=r.id == current) for r in rows]


@router.delete("/sessions/{session_id}", response_model=Message)
def revoke_session(session_id: int, db: DB, user: CurrentUser):  # noqa: ANN201
    row = db.get(RefreshToken, session_id)
    if not row or row.user_id != user.id:
        raise NotFoundError("Session not found")
    row.revoked_at = utcnow()
    db.commit()
    return Message(message="Session signed out")
