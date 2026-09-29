from fastapi import APIRouter, Request

from app.api.deps import DB, CurrentUser
from app.core.config import settings
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
from app.schemas.common import Message
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _me(user) -> MeOut:  # type: ignore[no-untyped-def]
    base = UserOut.model_validate(user).model_dump()
    return MeOut(**base, permissions=sorted(user.permission_codes), landing_path=auth_service.landing_path(user))


class LoginResponse(TokenPair):
    user: MeOut


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: DB):  # noqa: ANN201
    user, tokens = auth_service.login(db, body.email, body.password, body.otp, request)
    return LoginResponse(**tokens.model_dump(), user=_me(user))


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, request: Request, db: DB):  # noqa: ANN201
    return auth_service.refresh(db, body.refresh_token, request)


@router.post("/logout", response_model=Message)
def logout(request: Request, db: DB, user: CurrentUser):  # noqa: ANN201
    auth_service.logout(db, user, getattr(request.state, "session_id", None), request)
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
