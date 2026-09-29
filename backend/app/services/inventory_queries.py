"""Read-side inventory queries shared by the API, dashboard, reports and alerts."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.catalog import Product
from app.models.inventory import Inventory, InventoryBatch
from app.services import settings_service

ZERO = Decimal("0")


def batch_value_subquery():  # noqa: ANN201
    return (
        select(InventoryBatch.product_id.label("product_id"),
               func.coalesce(func.sum(InventoryBatch.quantity_remaining * InventoryBatch.purchase_cost), 0).label("value"))
        .where(InventoryBatch.quantity_remaining > 0)
        .group_by(InventoryBatch.product_id)
        .subquery()
    )


def stock_status(current: Decimal, reorder: Decimal) -> str:
    if current <= 0:
        return "out"
    if current <= reorder:
        return "low"
    return "ok"


def low_stock_filter():  # noqa: ANN201
    return (Product.is_deleted.is_(False), Product.is_active.is_(True), Inventory.current_stock <= Product.reorder_level,
            Inventory.current_stock > 0)


def out_of_stock_filter():  # noqa: ANN201
    return (Product.is_deleted.is_(False), Product.is_active.is_(True), Inventory.current_stock <= 0)


def expiring_batches_stmt(days: int, today: date | None = None) -> Select:  # type: ignore[type-arg]
    today = today or date.today()
    return (
        select(InventoryBatch)
        .where(InventoryBatch.quantity_remaining > 0, InventoryBatch.expiry_date.is_not(None),
               InventoryBatch.expiry_date >= today, InventoryBatch.expiry_date <= today + timedelta(days=days))
        .order_by(InventoryBatch.expiry_date)
    )


def expired_batches_stmt(today: date | None = None) -> Select:  # type: ignore[type-arg]
    today = today or date.today()
    return (
        select(InventoryBatch)
        .where(InventoryBatch.quantity_remaining > 0, InventoryBatch.expiry_date.is_not(None),
               InventoryBatch.expiry_date < today)
        .order_by(InventoryBatch.expiry_date)
    )


def summary(db: Session, *, with_value: bool) -> dict:  # type: ignore[type-arg]
    days = int(settings_service.get(db, "inventory.expiry_warning_days"))
    base = select(func.count()).select_from(Inventory).join(Product, Product.id == Inventory.product_id)
    low = db.scalar(base.where(*low_stock_filter())) or 0
    out = db.scalar(base.where(*out_of_stock_filter())) or 0
    total_products = db.scalar(select(func.count()).select_from(Product).where(Product.is_deleted.is_(False), Product.is_active.is_(True))) or 0
    units = db.scalar(select(func.coalesce(func.sum(Inventory.current_stock), 0)).join(Product, Product.id == Inventory.product_id)
                      .where(Product.is_deleted.is_(False))) or ZERO
    value = db.scalar(select(func.coalesce(func.sum(InventoryBatch.quantity_remaining * InventoryBatch.purchase_cost), 0))
                      .where(InventoryBatch.quantity_remaining > 0)) or ZERO
    expiring = db.scalar(select(func.count(func.distinct(InventoryBatch.product_id))).where(
        InventoryBatch.id.in_(select(expiring_batches_stmt(days).subquery().c.id)))) or 0
    expired = db.scalar(select(func.count(func.distinct(InventoryBatch.product_id))).where(
        InventoryBatch.id.in_(select(expired_batches_stmt().subquery().c.id)))) or 0
    healthy = max(total_products - low - out, 0)
    return {
        "stock_value": Decimal(str(value)) if with_value else None, "total_units": Decimal(str(units)),
        "product_count": total_products, "low_stock_count": low, "out_of_stock_count": out,
        "expiring_soon_count": expiring, "expired_count": expired, "healthy_count": healthy,
    }
