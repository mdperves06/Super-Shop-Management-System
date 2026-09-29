from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Pagination, has_permission, require
from app.models.auth import User
from app.models.catalog import Product, ProductBarcode
from app.models.inventory import Inventory, InventoryBatch, InventoryTransaction, StockAdjustment
from app.repositories.base import like, page_response, paginate
from app.schemas.common import Page
from app.schemas.inventory import (
    AdjustmentCreate,
    AdjustmentOut,
    BatchOut,
    InventorySummary,
    MovementOut,
    StockRow,
)
from app.services import catalog_service, inventory_queries, inventory_service, settings_service
from app.utils.dates import get_tz, range_bounds

router = APIRouter(prefix="/inventory", tags=["inventory"])
Reader = Annotated[User, Depends(require("inventory.read"))]


def _stock_row(product: Product, inv: Inventory, value, can_cost: bool) -> StockRow:  # noqa: ANN001
    cat = product.category.name if product.category else None
    return StockRow(
        product_id=product.id, sku=product.sku, barcode=product.barcode, name=product.name, category=cat,
        unit=product.unit.short_name, current_stock=inv.current_stock, reserved_stock=inv.reserved_stock,
        available_stock=inv.available_stock, damaged_stock=inv.damaged_stock, expired_stock=inv.expired_stock,
        reorder_level=product.reorder_level, stock_value=value if can_cost else None,
        status=inventory_queries.stock_status(inv.current_stock, product.reorder_level),
    )


@router.get("/summary", response_model=InventorySummary)
def summary(db: DB, user: Reader):
    return inventory_queries.summary(db, with_value=has_permission(user, "product.cost"))


@router.get("/stock", response_model=Page[StockRow])
def stock(db: DB, p: Pagination, user: Reader, category_id: int | None = None, status: str | None = None,
          supplier_id: int | None = None):
    vals = inventory_queries.batch_value_subquery()
    stmt = (
        select(Product, Inventory, func.coalesce(vals.c.value, 0))
        .join(Inventory, Inventory.product_id == Product.id)
        .outerjoin(vals, vals.c.product_id == Product.id)
        .where(Product.is_deleted.is_(False))
    )
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(Product.name.ilike(t, escape="\\"), Product.sku.ilike(t, escape="\\"),
                              Product.barcodes.any(ProductBarcode.barcode.ilike(t, escape="\\"))))
    if category_id:
        stmt = stmt.where(or_(Product.category_id == category_id, Product.subcategory_id == category_id))
    if supplier_id:
        stmt = stmt.where(Product.supplier_id == supplier_id)
    if status == "out":
        stmt = stmt.where(Inventory.current_stock <= 0)
    elif status == "low":
        stmt = stmt.where(Inventory.current_stock > 0, Inventory.current_stock <= Product.reorder_level)
    elif status == "ok":
        stmt = stmt.where(Inventory.current_stock > Product.reorder_level)
    stmt = stmt.order_by(Product.name)
    rows, total = paginate(db, stmt, p, scalars=False)
    can_cost = has_permission(user, "product.cost")
    return page_response([_stock_row(pr, inv, val, can_cost) for pr, inv, val in rows], total, p)


@router.get("/low-stock", response_model=Page[StockRow])
def low_stock(db: DB, p: Pagination, user: Reader):
    vals = inventory_queries.batch_value_subquery()
    stmt = (
        select(Product, Inventory, func.coalesce(vals.c.value, 0))
        .join(Inventory, Inventory.product_id == Product.id)
        .outerjoin(vals, vals.c.product_id == Product.id)
        .where(Product.is_deleted.is_(False), Product.is_active.is_(True), Inventory.current_stock <= Product.reorder_level)
        .order_by(Inventory.current_stock, Product.name)
    )
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(Product.name.ilike(t, escape="\\"), Product.sku.ilike(t, escape="\\")))
    rows, total = paginate(db, stmt, p, scalars=False)
    can_cost = has_permission(user, "product.cost")
    return page_response([_stock_row(pr, inv, val, can_cost) for pr, inv, val in rows], total, p)


def _batch_out(b: InventoryBatch, can_cost: bool) -> BatchOut:
    days = (b.expiry_date - date.today()).days if b.expiry_date else None
    return BatchOut(
        id=b.id, product_id=b.product_id, product_name=b.product.name, sku=b.product.sku, batch_number=b.batch_number,
        manufacturing_date=b.manufacturing_date, expiry_date=b.expiry_date, days_to_expiry=days,
        purchase_cost=b.purchase_cost if can_cost else None, quantity_received=b.quantity_received,
        quantity_remaining=b.quantity_remaining,
        stock_value=(b.quantity_remaining * b.purchase_cost) if can_cost else None, received_at=b.received_at,
    )


@router.get("/batches", response_model=Page[BatchOut])
def batches(db: DB, p: Pagination, user: Reader, product_id: int | None = None, include_empty: bool = False):
    stmt = select(InventoryBatch).join(Product, Product.id == InventoryBatch.product_id)
    if product_id:
        stmt = stmt.where(InventoryBatch.product_id == product_id)
    if not include_empty:
        stmt = stmt.where(InventoryBatch.quantity_remaining > 0)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(Product.name.ilike(t, escape="\\"), Product.sku.ilike(t, escape="\\"),
                              InventoryBatch.batch_number.ilike(t, escape="\\")))
    stmt = stmt.order_by(InventoryBatch.expiry_date.is_(None), InventoryBatch.expiry_date, InventoryBatch.id)
    rows, total = paginate(db, stmt, p)
    can_cost = has_permission(user, "product.cost")
    return page_response([_batch_out(b, can_cost) for b in rows], total, p)


@router.get("/expiring", response_model=Page[BatchOut])
def expiring(db: DB, p: Pagination, user: Reader, days: int | None = None):
    days = days if days is not None else int(settings_service.get(db, "inventory.expiry_warning_days"))
    rows, total = paginate(db, inventory_queries.expiring_batches_stmt(min(max(days, 1), 730)), p)
    can_cost = has_permission(user, "product.cost")
    return page_response([_batch_out(b, can_cost) for b in rows], total, p)


@router.get("/expired", response_model=Page[BatchOut])
def expired(db: DB, p: Pagination, user: Reader):
    rows, total = paginate(db, inventory_queries.expired_batches_stmt(), p)
    can_cost = has_permission(user, "product.cost")
    return page_response([_batch_out(b, can_cost) for b in rows], total, p)


@router.get("/movements", response_model=Page[MovementOut])
def movements(
    db: DB, p: Pagination, user: Reader, product_id: int | None = None, txn_type: str | None = None,
    start: date | None = None, end: date | None = None, batch_id: int | None = None,
):
    stmt = select(InventoryTransaction).join(Product, Product.id == InventoryTransaction.product_id)
    if product_id:
        stmt = stmt.where(InventoryTransaction.product_id == product_id)
    if batch_id:
        stmt = stmt.where(InventoryTransaction.batch_id == batch_id)
    if txn_type:
        stmt = stmt.where(InventoryTransaction.txn_type == txn_type)
    if start and end:
        lo, hi = range_bounds(start, end, get_tz(settings_service.get(db, "locale.timezone")))
        stmt = stmt.where(InventoryTransaction.created_at >= lo, InventoryTransaction.created_at < hi)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(Product.name.ilike(t, escape="\\"), Product.sku.ilike(t, escape="\\")))
    stmt = stmt.order_by(InventoryTransaction.id.desc())
    rows, total = paginate(db, stmt, p)
    can_cost = has_permission(user, "product.cost")
    batch_ids = {r.batch_id for r in rows if r.batch_id}
    batch_numbers = dict(db.execute(select(InventoryBatch.id, InventoryBatch.batch_number)
                                    .where(InventoryBatch.id.in_(batch_ids))).all()) if batch_ids else {}
    user_ids = {r.user_id for r in rows if r.user_id}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids))).all()) if user_ids else {}
    items = [
        MovementOut(
            id=r.id, created_at=r.created_at, product_id=r.product_id, product_name=r.product.name, sku=r.product.sku,
            batch_id=r.batch_id, batch_number=batch_numbers.get(r.batch_id), txn_type=r.txn_type, quantity=r.quantity,
            balance_after=r.balance_after, unit_cost=r.unit_cost if can_cost else None,
            reference_type=r.reference_type, reference_id=r.reference_id, reason=r.reason, user_name=names.get(r.user_id),
        )
        for r in rows
    ]
    return page_response(items, total, p)


@router.get("/adjustments", response_model=Page[AdjustmentOut])
def list_adjustments(db: DB, p: Pagination, _: Reader, product_id: int | None = None):
    stmt = select(StockAdjustment).join(Product, Product.id == StockAdjustment.product_id)
    if product_id:
        stmt = stmt.where(StockAdjustment.product_id == product_id)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(Product.name.ilike(t, escape="\\"), StockAdjustment.adjustment_number.ilike(t, escape="\\")))
    rows, total = paginate(db, stmt.order_by(StockAdjustment.id.desc()), p)
    user_ids = {r.user_id for r in rows if r.user_id}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids))).all()) if user_ids else {}
    items = []
    for r in rows:
        out = AdjustmentOut.model_validate(r)
        out.product_name, out.user_name = r.product.name, names.get(r.user_id)
        items.append(out)
    return page_response(items, total, p)


@router.post("/adjustments", response_model=AdjustmentOut, status_code=201)
def create_adjustment(body: AdjustmentCreate, request: Request, db: DB, user: Annotated[User, Depends(require("inventory.adjust"))]):
    product = catalog_service.get_product(db, body.product_id)
    cost = body.unit_cost
    if cost is not None and not has_permission(user, "product.cost"):
        cost = None
    adj = inventory_service.adjust_stock(
        db, product, body.adjustment_type, body.quantity, body.reason, user, batch_id=body.batch_id,
        unit_cost=cost, expiry_date=body.expiry_date, batch_number=body.batch_number,
    )
    db.commit()
    out = AdjustmentOut.model_validate(adj)
    out.product_name, out.user_name = product.name, user.full_name
    return out
