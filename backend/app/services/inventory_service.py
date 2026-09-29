"""All stock movement goes through this module.

Guarantees:
  * every movement writes an immutable InventoryTransaction (never a silent stock edit)
  * decrements use conditional UPDATEs (`... WHERE qty >= :n`) so two cashiers can never
    both consume the same units, on any database
  * expiry-tracked stock is consumed First-Expire-First-Out, everything else First-In-First-Out
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import InsufficientStock, NotFoundError, ValidationFailed
from app.models.auth import User
from app.models.catalog import Product
from app.models.enums import AdjustmentType, InventoryTxnType
from app.models.inventory import Inventory, InventoryBatch, InventoryTransaction, StockAdjustment
from app.services import audit, numbering, settings_service
from app.services.pricing import q2, q3

ZERO = Decimal("0")


@dataclass
class Allocation:
    batch_id: int | None
    quantity: Decimal
    unit_cost: Decimal


def _lock_inventory(db: Session, product_id: int) -> Inventory:
    inv = db.execute(select(Inventory).where(Inventory.product_id == product_id).with_for_update()).scalar_one_or_none()
    if inv is None:
        raise NotFoundError("Inventory record not found for product")
    return inv


def _expire_inventory(db: Session, product_id: int) -> None:
    """Core UPDATEs bypass the ORM; drop any cached Inventory instance so it reloads fresh."""
    for obj in list(db.identity_map.values()):
        if isinstance(obj, Inventory) and obj.product_id == product_id:
            db.expire(obj)


def _stock(db: Session, product_id: int) -> Decimal:
    return db.scalar(select(Inventory.current_stock).where(Inventory.product_id == product_id)) or ZERO


def _log(db: Session, *, product_id: int, batch_id: int | None, txn_type: InventoryTxnType, quantity: Decimal,
         balance_after: Decimal, unit_cost: Decimal, reference_type: str | None, reference_id: int | None,
         reason: str | None, user: User | None) -> InventoryTransaction:
    row = InventoryTransaction(
        product_id=product_id, batch_id=batch_id, txn_type=txn_type.value, quantity=quantity,
        balance_after=balance_after, unit_cost=unit_cost, reference_type=reference_type,
        reference_id=reference_id, reason=reason, user_id=user.id if user else None,
    )
    db.add(row)
    return row


def _positive(qty: Decimal, what: str = "Quantity") -> Decimal:
    qty = q3(qty)
    if qty <= 0:
        raise ValidationFailed(f"{what} must be greater than zero", code="invalid_quantity")
    return qty


# ---- stock in -------------------------------------------------------------------------

def receive_stock(
    db: Session, product: Product, qty: Decimal, unit_cost: Decimal, *, user: User | None,
    txn_type: InventoryTxnType = InventoryTxnType.PURCHASE, batch_number: str | None = None,
    manufacturing_date: date | None = None, expiry_date: date | None = None, supplier_id: int | None = None,
    goods_receipt_id: int | None = None, reference_type: str | None = None, reference_id: int | None = None,
    reason: str | None = None,
) -> InventoryBatch:
    qty = _positive(qty)
    if unit_cost < 0:
        raise ValidationFailed("Cost cannot be negative")
    if product.track_expiry and expiry_date is None:
        raise ValidationFailed(f"{product.name} tracks expiry; an expiry date is required", code="expiry_required")
    if manufacturing_date and expiry_date and expiry_date < manufacturing_date:
        raise ValidationFailed("Expiry date cannot be before the manufacturing date")
    _lock_inventory(db, product.id)
    if not batch_number:
        batch_number = f"B{date.today():%Y%m%d}-{(db.scalar(select(InventoryBatch.id).order_by(InventoryBatch.id.desc()).limit(1)) or 0) + 1}"
    batch = InventoryBatch(
        product_id=product.id, batch_number=batch_number, manufacturing_date=manufacturing_date,
        expiry_date=expiry_date, purchase_cost=q2(unit_cost), quantity_received=qty, quantity_remaining=qty,
        supplier_id=supplier_id, goods_receipt_id=goods_receipt_id,
    )
    db.add(batch)
    db.flush()
    db.execute(update(Inventory).where(Inventory.product_id == product.id)
               .values(current_stock=Inventory.current_stock + qty), execution_options={"synchronize_session": False})
    balance = _stock(db, product.id)
    _log(db, product_id=product.id, batch_id=batch.id, txn_type=txn_type, quantity=qty, balance_after=balance,
         unit_cost=q2(unit_cost), reference_type=reference_type, reference_id=reference_id, reason=reason, user=user)
    _expire_inventory(db, product.id)
    return batch


# ---- stock out ------------------------------------------------------------------------

def issue_stock(
    db: Session, product: Product, qty: Decimal, *, txn_type: InventoryTxnType, user: User | None,
    reference_type: str | None = None, reference_id: int | None = None, reason: str | None = None,
    batch_id: int | None = None, allow_oversell: bool | None = None, allow_expired: bool | None = None,
    only_expired: bool = False,
) -> list[Allocation]:
    """Remove sellable stock, returning which batches (and at what cost) supplied it."""
    qty = _positive(qty)
    if allow_oversell is None:
        allow_oversell = settings_service.get_bool(db, "inventory.allow_oversell")
    if allow_expired is None:
        allow_expired = settings_service.get_bool(db, "inventory.allow_expired_sale")
    if batch_id is not None:  # explicit batch operations never oversell
        allow_oversell = False
    _lock_inventory(db, product.id)

    guard = update(Inventory).where(Inventory.product_id == product.id)
    if not allow_oversell:
        guard = guard.where(Inventory.current_stock >= qty)
    result = db.execute(guard.values(current_stock=Inventory.current_stock - qty),
                        execution_options={"synchronize_session": False})
    if result.rowcount != 1:
        raise InsufficientStock(
            f"Insufficient stock for {product.name}: requested {qty}, available {_stock(db, product.id)}",
            details={"product_id": product.id, "requested": float(qty), "available": float(_stock(db, product.id))},
        )
    balance_after_all = _stock(db, product.id)
    running = balance_after_all + qty  # balance before this movement

    today = date.today()
    stmt = select(InventoryBatch).where(InventoryBatch.product_id == product.id, InventoryBatch.quantity_remaining > 0)
    if batch_id is not None:
        stmt = stmt.where(InventoryBatch.id == batch_id)
    if only_expired:
        stmt = stmt.where(InventoryBatch.expiry_date.is_not(None), InventoryBatch.expiry_date < today)
    elif not allow_expired:
        stmt = stmt.where((InventoryBatch.expiry_date.is_(None)) | (InventoryBatch.expiry_date >= today))
    stmt = stmt.order_by(InventoryBatch.expiry_date.is_(None), InventoryBatch.expiry_date,
                         InventoryBatch.received_at, InventoryBatch.id).with_for_update()
    allocations: list[Allocation] = []
    remaining = qty
    for batch in db.scalars(stmt).all():
        if remaining <= 0:
            break
        take = min(remaining, Decimal(batch.quantity_remaining))
        res = db.execute(
            update(InventoryBatch).where(InventoryBatch.id == batch.id, InventoryBatch.quantity_remaining >= take)
            .values(quantity_remaining=InventoryBatch.quantity_remaining - take),
            execution_options={"synchronize_session": False})
        if res.rowcount != 1:  # lost a race for this batch
            continue
        running -= take
        allocations.append(Allocation(batch.id, take, Decimal(batch.purchase_cost)))
        _log(db, product_id=product.id, batch_id=batch.id, txn_type=txn_type, quantity=-take, balance_after=running,
             unit_cost=Decimal(batch.purchase_cost), reference_type=reference_type, reference_id=reference_id,
             reason=reason, user=user)
        remaining -= take
    if remaining > 0:
        if allow_oversell:
            running -= remaining
            cost = Decimal(product.purchase_price)
            allocations.append(Allocation(None, remaining, cost))
            _log(db, product_id=product.id, batch_id=None, txn_type=txn_type, quantity=-remaining, balance_after=running,
                 unit_cost=cost, reference_type=reference_type, reference_id=reference_id,
                 reason=(reason or "") + " [oversold]", user=user)
        else:
            what = "expired" if only_expired else "sellable (non-expired)"
            raise InsufficientStock(
                f"Insufficient {what} stock for {product.name}: requested {qty}, could allocate {qty - remaining}",
                details={"product_id": product.id, "requested": float(qty), "available": float(qty - remaining)},
            )
    _expire_inventory(db, product.id)
    return allocations


def restock(
    db: Session, product: Product, allocations: list[tuple[int | None, Decimal, Decimal]], *,
    txn_type: InventoryTxnType, user: User | None, reference_type: str, reference_id: int, reason: str | None,
) -> None:
    """Put returned/voided units back into the batches they came from."""
    total = sum((a[1] for a in allocations), ZERO)
    if total <= 0:
        return
    _lock_inventory(db, product.id)
    db.execute(update(Inventory).where(Inventory.product_id == product.id)
               .values(current_stock=Inventory.current_stock + total), execution_options={"synchronize_session": False})
    running = _stock(db, product.id) - total
    for batch_id, qty, cost in allocations:
        if batch_id is not None:
            db.execute(update(InventoryBatch).where(InventoryBatch.id == batch_id)
                       .values(quantity_remaining=InventoryBatch.quantity_remaining + qty),
                       execution_options={"synchronize_session": False})
        running += qty
        _log(db, product_id=product.id, batch_id=batch_id, txn_type=txn_type, quantity=qty, balance_after=running,
             unit_cost=cost, reference_type=reference_type, reference_id=reference_id, reason=reason, user=user)
    _expire_inventory(db, product.id)


# ---- adjustments ----------------------------------------------------------------------

def adjust_stock(
    db: Session, product: Product, adj_type: AdjustmentType, qty: Decimal, reason: str, user: User, *,
    batch_id: int | None = None, unit_cost: Decimal | None = None, expiry_date: date | None = None,
    batch_number: str | None = None,
) -> StockAdjustment:
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ValidationFailed("A reason is required for every stock adjustment", code="reason_required")
    qty = _positive(qty)
    number = numbering.next_number(db, "ADJ")
    adj = StockAdjustment(adjustment_number=number, product_id=product.id, batch_id=batch_id,
                          adjustment_type=adj_type.value, quantity=qty, reason=reason, user_id=user.id)
    db.add(adj)
    db.flush()
    ref = ("stock_adjustment", adj.id)

    if adj_type is AdjustmentType.IN:
        if batch_id is not None:
            batch = db.get(InventoryBatch, batch_id)
            if not batch or batch.product_id != product.id:
                raise NotFoundError("Batch not found for this product")
            _lock_inventory(db, product.id)
            db.execute(update(InventoryBatch).where(InventoryBatch.id == batch_id)
                       .values(quantity_remaining=InventoryBatch.quantity_remaining + qty),
                       execution_options={"synchronize_session": False})
            db.execute(update(Inventory).where(Inventory.product_id == product.id)
                       .values(current_stock=Inventory.current_stock + qty), execution_options={"synchronize_session": False})
            _log(db, product_id=product.id, batch_id=batch_id, txn_type=InventoryTxnType.ADJUSTMENT_IN, quantity=qty,
                 balance_after=_stock(db, product.id), unit_cost=Decimal(batch.purchase_cost),
                 reference_type=ref[0], reference_id=ref[1], reason=reason, user=user)
        else:
            cost = unit_cost if unit_cost is not None else Decimal(product.purchase_price)
            batch = receive_stock(db, product, qty, cost, user=user, txn_type=InventoryTxnType.ADJUSTMENT_IN,
                                  batch_number=batch_number or f"ADJ-{number}", expiry_date=expiry_date,
                                  reference_type=ref[0], reference_id=ref[1], reason=reason)
            adj.batch_id = batch.id
    elif adj_type is AdjustmentType.OUT:
        issue_stock(db, product, qty, txn_type=InventoryTxnType.ADJUSTMENT_OUT, user=user, reference_type=ref[0],
                    reference_id=ref[1], reason=reason, batch_id=batch_id, allow_oversell=False, allow_expired=True)
    else:
        txn = InventoryTxnType.DAMAGE if adj_type is AdjustmentType.DAMAGE else InventoryTxnType.EXPIRED
        issue_stock(db, product, qty, txn_type=txn, user=user, reference_type=ref[0], reference_id=ref[1],
                    reason=reason, batch_id=batch_id, allow_oversell=False, allow_expired=True,
                    only_expired=(adj_type is AdjustmentType.EXPIRED and batch_id is None))
        column = Inventory.damaged_stock if adj_type is AdjustmentType.DAMAGE else Inventory.expired_stock
        db.execute(update(Inventory).where(Inventory.product_id == product.id).values({column.key: column + qty}),
                   execution_options={"synchronize_session": False})

    _expire_inventory(db, product.id)
    audit.record(db, user=user, action="inventory.adjust", entity="product", entity_id=product.id,
                 new={"type": adj_type.value, "quantity": qty, "reason": reason, "number": number})
    return adj
