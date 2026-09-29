import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings
from app.core.errors import AuthenticationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def _encode(payload: dict[str, Any], secret: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    body = {**payload, "iat": now, "exp": now + expires}
    return jwt.encode(body, secret, algorithm="HS256")


def create_access_token(user_id: int, session_id: int | None = None) -> str:
    return _encode(
        {"sub": str(user_id), "type": "access", "sid": session_id},
        settings.jwt_secret,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: int, jti: str) -> str:
    return _encode(
        {"sub": str(user_id), "type": "refresh", "jti": jti},
        settings.refresh_token_secret,
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, *, refresh: bool = False) -> dict[str, Any]:
    secret = settings.refresh_token_secret if refresh else settings.jwt_secret
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid token", code="token_invalid") from exc
    expected = "refresh" if refresh else "access"
    if payload.get("type") != expected:
        raise AuthenticationError("Invalid token type", code="token_invalid")
    return payload
