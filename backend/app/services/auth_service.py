import logging
import secrets
from datetime import timedelta

import pyotp
from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, ConflictError, NotFoundError, ValidationFailed
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.models.auth import PasswordResetToken, RefreshToken, Role, User
from app.models.base import utcnow
from app.schemas.auth import TokenPair
from app.services import audit
from app.services.mailer import send_email

log = logging.getLogger("app.auth")

# Where a user lands after login, first match wins.
LANDING = [
    ("dashboard.view", "/dashboard"),
    ("sale.create", "/pos"),
    ("product.read", "/products"),
    ("inventory.read", "/inventory"),
]


def landing_path(user: User) -> str:
    codes = user.permission_codes
    for perm, path in LANDING:
        if perm in codes:
            return path
    return "/profile"


def _issue_tokens(db: Session, user: User, request: Request | None) -> TokenPair:
    jti = new_opaque_token()
    ip, ua = audit.client_info(request)
    row = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(jti),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
        ip_address=ip,
        user_agent=ua,
    )
    db.add(row)
    db.flush()
    return TokenPair(
        access_token=create_access_token(user.id, row.id),
        refresh_token=create_refresh_token(user.id, jti),
        expires_in=settings.access_token_expire_minutes * 60,
    )


def login(db: Session, email: str, password: str, otp: str | None, request: Request | None) -> tuple[User, TokenPair]:
    user = db.scalar(select(User).where(User.email == email.lower(), User.is_deleted.is_(False)))
    generic = AuthenticationError("Invalid email or password", code="invalid_credentials")
    now = utcnow()
    if user is None:
        # equalise timing so unknown emails are not distinguishable
        verify_password(password, hash_password("dummy-password-1"))
        raise generic
    if user.locked_until and user.locked_until > now:
        minutes = int((user.locked_until - now).total_seconds() // 60) + 1
        raise AuthenticationError(f"Account locked. Try again in {minutes} minute(s).", code="account_locked")
    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.login_max_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_attempts = 0
            audit.record(db, user=user, action="auth.lockout", entity="user", entity_id=user.id, request=request)
        db.commit()
        raise generic
    if not user.is_active:
        raise AuthenticationError("This account is disabled", code="account_disabled")
    if user.totp_enabled:
        if not otp:
            raise AuthenticationError("Two-factor code required", code="otp_required")
        if not pyotp.TOTP(user.totp_secret or "").verify(otp, valid_window=1):
            raise AuthenticationError("Invalid two-factor code", code="otp_invalid")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    tokens = _issue_tokens(db, user, request)
    audit.record(db, user=user, action="auth.login", entity="user", entity_id=user.id, request=request)
    db.commit()
    return user, tokens


ROTATION_GRACE = timedelta(seconds=20)


def _usable(row: RefreshToken) -> bool:
    """Live, or rotated moments ago. Several browser tabs may refresh with the same cookie at once; the
    loser of that race must still succeed. Tokens revoked by logout / password change never get grace."""
    if row.revoked_at is None:
        return True
    return row.replaced_at is not None and row.revoked_at == row.replaced_at and utcnow() - row.replaced_at <= ROTATION_GRACE


def refresh(db: Session, refresh_token: str, request: Request | None) -> TokenPair:
    payload = decode_token(refresh_token, refresh=True)
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(payload["jti"])))
    if row is None or row.expires_at < utcnow() or not _usable(row):
        raise AuthenticationError("Session expired, please sign in again", code="session_expired")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active or user.is_deleted:
        raise AuthenticationError("Account unavailable", code="account_disabled")
    if row.revoked_at is None:  # rotate: a refresh token is single-use (see ROTATION_GRACE for parallel tabs)
        row.revoked_at = row.replaced_at = utcnow()
    tokens = _issue_tokens(db, user, request)
    db.commit()
    return tokens


def logout(db: Session, user: User, session_id: int | None, request: Request | None) -> None:
    if session_id:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.id == session_id, RefreshToken.user_id == user.id)
            .values(revoked_at=utcnow())
        )
    audit.record(db, user=user, action="auth.logout", entity="user", entity_id=user.id, request=request)
    db.commit()


def revoke_all_sessions(db: Session, user_id: int) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def change_password(db: Session, user: User, current: str, new: str, request: Request | None) -> None:
    if not verify_password(current, user.password_hash):
        raise ValidationFailed("Current password is incorrect")
    user.password_hash = hash_password(new)
    user.must_change_password = False
    revoke_all_sessions(db, user.id)
    audit.record(db, user=user, action="auth.password_change", entity="user", entity_id=user.id, request=request)
    db.commit()


def request_password_reset(db: Session, email: str, request: Request | None) -> str | None:
    """Always succeeds from the caller's point of view. Returns the token only so dev/tests can use it."""
    user = db.scalar(select(User).where(User.email == email.lower(), User.is_deleted.is_(False), User.is_active.is_(True)))
    if user is None:
        return None
    token = secrets.token_urlsafe(32)
    # only the newest link works: retire any earlier unused ones
    db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)).values(used_at=utcnow()))
    db.add(PasswordResetToken(user_id=user.id, token_hash=hash_token(token), expires_at=utcnow() + timedelta(hours=1)))
    audit.record(db, user=user, action="auth.password_reset_requested", entity="user", entity_id=user.id, request=request)
    db.commit()
    link = f"{settings.frontend_url}/reset-password?token={token}"
    body = (
        f"Hello {user.full_name},\n\nSomeone asked to reset the password for your account. Use this link within 1 hour "
        f"(it works once):\n\n{link}\n\nIf this wasn't you, ignore this email; your password stays unchanged.\n"
    )
    if not send_email(user.email, "Reset your password", body):
        if settings.is_production:
            log.warning("Password reset requested for user %s but email could not be sent (check SMTP_* settings)", user.id)
        else:
            log.info("SMTP not available; dev password reset link for %s: %s", user.email, link)
    return token


def reset_password(db: Session, token: str, new_password: str, request: Request | None) -> None:
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)))
    if row is None or row.used_at is not None or row.expires_at < utcnow():
        raise ValidationFailed("This reset link is invalid or has expired", code="invalid_reset_token")
    user = db.get(User, row.user_id)
    if user is None:
        raise NotFoundError("User not found")
    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    row.used_at = utcnow()
    revoke_all_sessions(db, user.id)
    audit.record(db, user=user, action="auth.password_reset", entity="user", entity_id=user.id, request=request)
    db.commit()


def totp_setup(db: Session, user: User) -> tuple[str, str]:
    if user.totp_enabled:
        raise ConflictError("Two-factor authentication is already enabled")
    user.totp_secret = pyotp.random_base32()
    db.commit()
    uri = pyotp.TOTP(user.totp_secret).provisioning_uri(name=user.email, issuer_name="Super Shop")
    return user.totp_secret, uri


def totp_enable(db: Session, user: User, code: str) -> None:
    if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
        raise ValidationFailed("Invalid two-factor code")
    user.totp_enabled = True
    audit.record(db, user=user, action="auth.2fa_enabled", entity="user", entity_id=user.id)
    db.commit()


def totp_disable(db: Session, user: User, code: str) -> None:
    if not user.totp_enabled or not pyotp.TOTP(user.totp_secret or "").verify(code, valid_window=1):
        raise ValidationFailed("Invalid two-factor code")
    user.totp_enabled = False
    user.totp_secret = None
    audit.record(db, user=user, action="auth.2fa_disabled", entity="user", entity_id=user.id)
    db.commit()


def create_user(
    db: Session, *, email: str, full_name: str, password: str, role_ids: list[int], phone: str | None = None,
    max_discount_percent=None, must_change_password: bool = False,
) -> User:
    email = email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise ConflictError("A user with this email already exists")
    roles = list(db.scalars(select(Role).where(Role.id.in_(role_ids))))
    if len(roles) != len(set(role_ids)):
        raise ValidationFailed("One or more roles do not exist")
    user = User(
        email=email, full_name=full_name, phone=phone, password_hash=hash_password(password),
        max_discount_percent=max_discount_percent, must_change_password=must_change_password,
    )
    user.roles = roles
    db.add(user)
    db.flush()
    return user
