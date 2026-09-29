from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthenticationError, PermissionDenied
from app.core.security import decode_token
from app.models.auth import RefreshToken, User
from app.schemas.common import PageParams

bearer = HTTPBearer(auto_error=False, description="JWT access token")

DB = Annotated[Session, Depends(get_db)]


def get_current_user(
    request: Request,
    db: DB,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if creds is None:
        raise AuthenticationError("Not authenticated", code="not_authenticated")
    payload = decode_token(creds.credentials)
    user = db.get(User, int(payload["sub"]))
    if user is None or user.is_deleted or not user.is_active:
        raise AuthenticationError("Account unavailable", code="account_disabled")
    sid = payload.get("sid")
    if sid:
        session = db.get(RefreshToken, sid)
        if session is None or session.revoked_at is not None:
            raise AuthenticationError("Session ended, please sign in again", code="session_expired")
    request.state.session_id = sid
    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require(*permissions: str, any_of: bool = False) -> Callable[..., User]:
    """Dependency factory enforcing permissions on the server, independent of the UI."""

    def checker(user: CurrentUser) -> User:
        held = user.permission_codes
        ok = any(p in held for p in permissions) if any_of else all(p in held for p in permissions)
        if not ok:
            raise PermissionDenied("You do not have permission to perform this action", details={"required": list(permissions)})
        return user

    return checker


def has_permission(user: User, code: str) -> bool:
    return code in user.permission_codes


def page_params(page: int = 1, page_size: int = 20, search: str | None = None, sort: str | None = None) -> PageParams:
    return PageParams(page, page_size, search, sort)


Pagination = Annotated[PageParams, Depends(page_params)]
