from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.system import Setting

# key -> (default, group, is_public)
DEFAULT_SETTINGS: dict[str, tuple[Any, str, bool]] = {
    "shop.name": ("Super Shop", "shop", True),
    "shop.address": ("House 12, Road 5, Dhanmondi, Dhaka", "shop", True),
    "shop.phone": ("+880 1700-000000", "shop", True),
    "shop.email": ("info@supershop.example", "shop", True),
    "shop.logo": ("", "shop", True),
    "shop.bin": ("", "shop", True),
    "locale.currency": ("BDT", "locale", True),
    "locale.currency_symbol": ("৳", "locale", True),
    "locale.timezone": ("Asia/Dhaka", "locale", True),
    "locale.language": ("en", "locale", True),
    "locale.date_format": ("DD/MM/YYYY", "locale", True),
    "tax.prices_include_tax": (True, "tax", True),
    "receipt.header": ("", "receipt", True),
    "receipt.footer": ("Thank you for shopping with us!", "receipt", True),
    "receipt.show_tax": (True, "receipt", True),
    "receipt.paper_width_mm": (80, "receipt", True),
    "numbering.invoice_prefix": ("INV", "numbering", False),
    "numbering.purchase_prefix": ("PUR", "numbering", False),
    "numbering.return_prefix": ("RET", "numbering", False),
    "inventory.low_stock_threshold": (10, "inventory", False),
    "inventory.expiry_warning_days": (30, "inventory", False),
    "inventory.valuation_method": ("FIFO", "inventory", False),
    "inventory.allow_oversell": (False, "inventory", False),
    "inventory.allow_expired_sale": (False, "inventory", False),
    "pos.require_open_register": (True, "pos", True),
    "pos.cashier_max_discount_percent": (5, "pos", True),
    "pos.allow_guest_credit": (False, "pos", False),
    "pos.default_payment_method": ("CASH", "pos", True),
    "pos.loyalty_points_per_100": (1, "pos", False),
}


def ensure_defaults(db: Session) -> None:
    existing = {s.key for s in db.scalars(select(Setting))}
    for key, (value, group, public) in DEFAULT_SETTINGS.items():
        if key not in existing:
            db.add(Setting(key=key, value=value, group=group, is_public=public))
    db.flush()


def get_all(db: Session, *, public_only: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {k: v[0] for k, v in DEFAULT_SETTINGS.items() if not public_only or v[2]}
    stmt = select(Setting)
    if public_only:
        stmt = stmt.where(Setting.is_public.is_(True))
    for s in db.scalars(stmt):
        result[s.key] = s.value
    return result


def get(db: Session, key: str) -> Any:
    row = db.scalar(select(Setting).where(Setting.key == key))
    if row is not None:
        return row.value
    return DEFAULT_SETTINGS[key][0]


def get_bool(db: Session, key: str) -> bool:
    return bool(get(db, key))


def get_decimal(db: Session, key: str):  # noqa: ANN201
    from decimal import Decimal

    return Decimal(str(get(db, key) or 0))


def set_value(db: Session, key: str, value: Any) -> tuple[Any, Any]:
    """Returns (old, new). Only known keys may be written."""
    if key not in DEFAULT_SETTINGS:
        from app.core.errors import ValidationFailed

        raise ValidationFailed(f"Unknown setting '{key}'")
    row = db.scalar(select(Setting).where(Setting.key == key))
    _, group, public = DEFAULT_SETTINGS[key]
    if row is None:
        row = Setting(key=key, value=value, group=group, is_public=public)
        db.add(row)
        old = DEFAULT_SETTINGS[key][0]
    else:
        old = row.value
        row.value = value
    db.flush()
    return old, value
