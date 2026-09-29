from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.system import AuditLog

SENSITIVE_KEYS = {"password", "password_hash", "totp_secret", "token", "refresh_token"}


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k in SENSITIVE_KEYS else _clean(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def snapshot(obj: Any, fields: list[str]) -> dict[str, Any]:
    return {f: _clean(getattr(obj, f, None)) for f in fields}


def client_info(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    ip = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    ua = request.headers.get("user-agent")
    return ip, (ua[:250] if ua else None)


def record(
    db: Session,
    *,
    user: User | None,
    action: str,
    entity: str,
    entity_id: int | str | None = None,
    old: Any = None,
    new: Any = None,
    description: str | None = None,
    request: Request | None = None,
) -> AuditLog:
    ip, ua = client_info(request)
    row = AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        description=description,
        old_value=_clean(old) if old is not None else None,
        new_value=_clean(new) if new is not None else None,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(row)
    return row
