from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.api.deps import DB, CurrentUser, Pagination, has_permission, require
from app.models.auth import User
from app.models.finance import PaymentMethod
from app.models.system import AuditLog
from app.repositories.base import like, page_response, paginate
from app.schemas.common import Num, ORMModel, Page, UTCDateTime
from app.services import audit, settings_service
from app.utils.dates import get_tz, range_bounds
from app.utils.uploads import IMAGE_TYPES, save_upload

router = APIRouter(tags=["system"])


class AuditOut(ORMModel):
    id: int
    created_at: UTCDateTime
    user_id: int | None
    user_email: str | None
    action: str
    entity: str
    entity_id: str | None
    description: str | None
    old_value: Any | None
    new_value: Any | None
    ip_address: str | None


@router.get("/audit-logs", response_model=Page[AuditOut])
def audit_logs(
    db: DB, p: Pagination, _: Annotated[User, Depends(require("audit.read"))], entity: str | None = None,
    entity_id: str | None = None, action: str | None = None, user_id: int | None = None,
    start: date | None = None, end: date | None = None,
):
    stmt = select(AuditLog)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action) if action.endswith(".") else AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if start and end:
        lo, hi = range_bounds(start, end, get_tz(settings_service.get(db, "locale.timezone")))
        stmt = stmt.where(AuditLog.created_at >= lo, AuditLog.created_at < hi)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(AuditLog.action.ilike(t, escape="\\"), AuditLog.user_email.ilike(t, escape="\\"),
                              AuditLog.description.ilike(t, escape="\\"), AuditLog.entity_id == p.search))
    rows, total = paginate(db, stmt.order_by(AuditLog.id.desc()), p)
    return page_response([AuditOut.model_validate(r) for r in rows], total, p)


# ---- settings -------------------------------------------------------------------------

@router.get("/settings/public")
def public_settings(db: DB):
    """Branding/locale needed before login (shop name, logo, language)."""
    return settings_service.get_all(db, public_only=True)


@router.get("/settings")
def all_settings(db: DB, user: CurrentUser):
    if has_permission(user, "settings.read"):
        return settings_service.get_all(db)
    return settings_service.get_all(db, public_only=True)


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


@router.put("/settings")
def update_settings(body: SettingsUpdate, request: Request, db: DB, user: Annotated[User, Depends(require("settings.update"))]):
    from app.core.errors import ValidationFailed

    old_new: dict[str, dict[str, Any]] = {}
    for key, value in body.values.items():
        _validate_setting(key, value)
        old, new = settings_service.set_value(db, key, value)
        if old != new:
            old_new[key] = {"old": old, "new": new}
    if old_new:
        audit.record(db, user=user, action="settings.update", entity="settings",
                     old={k: v["old"] for k, v in old_new.items()}, new={k: v["new"] for k, v in old_new.items()}, request=request)
    db.commit()
    return settings_service.get_all(db)


def _validate_setting(key: str, value: Any) -> None:
    from app.core.errors import ValidationFailed

    numeric = {"inventory.low_stock_threshold", "inventory.expiry_warning_days", "pos.cashier_max_discount_percent",
               "pos.loyalty_points_per_100", "receipt.paper_width_mm"}
    if key in numeric:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValidationFailed(f"{key} must be a non-negative number")
        if key == "pos.cashier_max_discount_percent" and value > 100:
            raise ValidationFailed("Discount limit cannot exceed 100%")
    if key == "inventory.valuation_method" and value != "FIFO":
        raise ValidationFailed("Only FIFO valuation is supported (FEFO for expiry-tracked goods)")
    if key == "locale.language" and value not in ("en", "bn"):
        raise ValidationFailed("Language must be 'en' or 'bn'")
    if key == "locale.timezone":
        from zoneinfo import ZoneInfo

        try:
            ZoneInfo(str(value))
        except Exception as exc:  # noqa: BLE001
            raise ValidationFailed("Unknown timezone") from exc
    if key.startswith("numbering.") and (not isinstance(value, str) or not value.isalnum() or len(value) > 8):
        raise ValidationFailed("Numbering prefix must be 1-8 letters/digits")


@router.post("/settings/logo")
async def upload_logo(db: DB, user: Annotated[User, Depends(require("settings.update"))], file: UploadFile = File(...)):
    path, _, _, _ = await save_upload(file, subdir="products", allowed=IMAGE_TYPES)
    old, _ = settings_service.set_value(db, "shop.logo", path)
    audit.record(db, user=user, action="settings.logo", entity="settings", old={"logo": old}, new={"logo": path})
    db.commit()
    return {"path": path}


# ---- payment methods ------------------------------------------------------------------

class PaymentMethodIn(BaseModel):
    code: str
    name: str
    method_type: str = "OTHER"
    requires_reference: bool = False
    is_active: bool = True
    sort_order: int = 0


class PaymentMethodOut(ORMModel):
    id: int
    code: str
    name: str
    method_type: str
    requires_reference: bool
    is_active: bool
    sort_order: int


@router.get("/payment-methods", response_model=list[PaymentMethodOut])
def payment_methods(db: DB, _: CurrentUser, include_inactive: bool = False):
    stmt = select(PaymentMethod).order_by(PaymentMethod.sort_order, PaymentMethod.id)
    if not include_inactive:
        stmt = stmt.where(PaymentMethod.is_active.is_(True))
    return list(db.scalars(stmt))


@router.post("/payment-methods", response_model=PaymentMethodOut, status_code=201)
def create_payment_method(body: PaymentMethodIn, request: Request, db: DB, user: Annotated[User, Depends(require("settings.update"))]):
    from app.core.errors import ConflictError, ValidationFailed

    code = body.code.strip().upper()
    if not code.replace("_", "").isalnum():
        raise ValidationFailed("Code must be letters, digits or underscore")
    if body.method_type not in ("CASH", "CARD", "MOBILE", "BANK", "OTHER"):
        raise ValidationFailed("Invalid payment method type")
    if db.scalar(select(PaymentMethod.id).where(PaymentMethod.code == code)):
        raise ConflictError("A payment method with this code already exists")
    row = PaymentMethod(**{**body.model_dump(), "code": code})
    db.add(row)
    db.flush()
    audit.record(db, user=user, action="payment_method.create", entity="payment_method", entity_id=row.id, new=body.model_dump(), request=request)
    db.commit()
    return row


@router.put("/payment-methods/{method_id}", response_model=PaymentMethodOut)
def update_payment_method(method_id: int, body: PaymentMethodIn, request: Request, db: DB, user: Annotated[User, Depends(require("settings.update"))]):
    from app.core.errors import NotFoundError, ValidationFailed

    row = db.get(PaymentMethod, method_id)
    if not row:
        raise NotFoundError("Payment method not found")
    if row.code == "CASH" and not body.is_active:
        raise ValidationFailed("The Cash payment method cannot be disabled")
    old = {"name": row.name, "is_active": row.is_active, "requires_reference": row.requires_reference}
    for k in ("name", "method_type", "requires_reference", "is_active", "sort_order"):
        setattr(row, k, getattr(body, k))
    audit.record(db, user=user, action="payment_method.update", entity="payment_method", entity_id=row.id, old=old, new=body.model_dump(), request=request)
    db.commit()
    return row
