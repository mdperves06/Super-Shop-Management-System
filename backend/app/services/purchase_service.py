from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models.auth import User
from app.models.base import utcnow
from app.models.enums import InventoryTxnType, LedgerType, PurchaseStatus
from app.models.inventory import InventoryBatch
from app.models.purchasing import (
    GoodsReceipt,
    PurchaseItem,
    PurchaseOrder,
    PurchaseReturn,
    PurchaseReturnItem,
    Supplier,
    SupplierProduct,
)
from app.schemas.purchasing import (
    PurchaseCreate,
    PurchaseItemIn,
    PurchaseReturnCreate,
    PurchaseUpdate,
    ReceiveIn,
)
from app.services import audit, catalog_service, inventory_service, ledger, numbering, settings_service
from app.services.pricing import q2

ZERO = Decimal("0")
EDITABLE = {PurchaseStatus.DRAFT.value}
RECEIVABLE = {PurchaseStatus.APPROVED.value, PurchaseStatus.PARTIALLY_RECEIVED.value}


def get_purchase(db: Session, purchase_id: int, *, lock: bool = False) -> PurchaseOrder:
    stmt = select(PurchaseOrder).where(PurchaseOrder.id == purchase_id)
    if lock:
        stmt = stmt.with_for_update()
    po = db.scalars(stmt).unique().first()
    if not po:
        raise NotFoundError("Purchase order not found")
    return po


def _line(data: PurchaseItemIn) -> dict:
    gross = q2(data.unit_cost * data.quantity)
    if data.discount_amount > gross:
        raise ValidationFailed("Line discount cannot exceed the line amount")
    net = gross - q2(data.discount_amount)
    tax = q2(net * data.tax_rate / 100)
    return {"tax_amount": tax, "line_total": net + tax}


def _apply_items(db: Session, po: PurchaseOrder, items: list[PurchaseItemIn]) -> None:
    po.items.clear()
    db.flush()
    subtotal = discount = tax = total = ZERO
    for data in items:
        product = catalog_service.get_product(db, data.product_id)
        calc = _line(data)
        po.items.append(PurchaseItem(
            product_id=product.id, quantity=data.quantity, unit_cost=q2(data.unit_cost),
            discount_amount=q2(data.discount_amount), tax_rate=data.tax_rate, **calc))
        subtotal += q2(data.unit_cost * data.quantity)
        discount += q2(data.discount_amount)
        tax += calc["tax_amount"]
        total += calc["line_total"]
    po.subtotal, po.discount_amount, po.tax_amount, po.total_amount = subtotal, discount, tax, total


def create_purchase(db: Session, data: PurchaseCreate, user: User) -> PurchaseOrder:
    supplier = db.get(Supplier, data.supplier_id)
    if not supplier or supplier.is_deleted or not supplier.is_active:
        raise ValidationFailed("Supplier not found or inactive")
    po = PurchaseOrder(
        po_number=numbering.next_number(db, settings_service.get(db, "numbering.purchase_prefix")),
        supplier_id=supplier.id, order_date=data.order_date or date.today(), expected_date=data.expected_date,
        notes=data.notes, created_by=user.id, status=PurchaseStatus.DRAFT.value,
    )
    db.add(po)
    db.flush()
    _apply_items(db, po, data.items)
    if data.submit:
        po.status = PurchaseStatus.PENDING.value
    audit.record(db, user=user, action="purchase.create", entity="purchase", entity_id=po.id,
                 new={"po": po.po_number, "supplier": supplier.name, "total": po.total_amount, "status": po.status})
    return po


def update_purchase(db: Session, po: PurchaseOrder, data: PurchaseUpdate, user: User) -> PurchaseOrder:
    if po.status not in EDITABLE:
        raise ConflictError("Only draft purchase orders can be edited", code="purchase_not_editable")
    changes = data.model_dump(exclude_unset=True, exclude={"items"})
    if "supplier_id" in changes and changes["supplier_id"] is not None:
        if not db.get(Supplier, changes["supplier_id"]):
            raise ValidationFailed("Supplier not found")
    for k, v in changes.items():
        if v is not None or k in ("expected_date", "notes"):
            setattr(po, k, v)
    if data.items is not None:
        _apply_items(db, po, data.items)
    audit.record(db, user=user, action="purchase.update", entity="purchase", entity_id=po.id, new={"total": po.total_amount})
    return po


def submit(db: Session, po: PurchaseOrder, user: User) -> PurchaseOrder:
    if po.status != PurchaseStatus.DRAFT.value:
        raise ConflictError("Only draft purchase orders can be submitted")
    po.status = PurchaseStatus.PENDING.value
    audit.record(db, user=user, action="purchase.submit", entity="purchase", entity_id=po.id)
    return po


def approve(db: Session, po: PurchaseOrder, user: User) -> PurchaseOrder:
    if po.status not in (PurchaseStatus.DRAFT.value, PurchaseStatus.PENDING.value):
        raise ConflictError(f"A {po.status.lower().replace('_', ' ')} purchase order cannot be approved")
    po.status = PurchaseStatus.APPROVED.value
    po.approved_by, po.approved_at = user.id, utcnow()
    audit.record(db, user=user, action="purchase.approve", entity="purchase", entity_id=po.id,
                 new={"po": po.po_number, "total": po.total_amount})
    return po


def cancel(db: Session, po: PurchaseOrder, reason: str, user: User) -> PurchaseOrder:
    if po.status in (PurchaseStatus.CANCELLED.value, PurchaseStatus.RECEIVED.value):
        raise ConflictError(f"A {po.status.lower()} purchase order cannot be cancelled")
    if any(i.received_quantity > 0 for i in po.items):
        raise ConflictError("Goods were already received against this order; use a purchase return instead",
                            code="purchase_already_received")
    po.status, po.cancelled_reason = PurchaseStatus.CANCELLED.value, reason
    audit.record(db, user=user, action="purchase.cancel", entity="purchase", entity_id=po.id, new={"reason": reason})
    return po


def receive(db: Session, po: PurchaseOrder, data: ReceiveIn, user: User) -> GoodsReceipt:
    """Stock and the supplier payable are created here — and only here."""
    if po.status not in RECEIVABLE:
        raise ConflictError("Only approved purchase orders can receive stock", code="purchase_not_receivable")
    items = {i.id: i for i in po.items}
    seen: set[int] = set()
    grn = GoodsReceipt(grn_number=numbering.next_number(db, "GRN"), purchase_id=po.id, received_by=user.id, notes=data.notes)
    db.add(grn)
    db.flush()
    total_value = ZERO
    for r in data.items:
        item = items.get(r.item_id)
        if item is None:
            raise ValidationFailed(f"Item {r.item_id} does not belong to this purchase order")
        if r.item_id in seen:
            raise ValidationFailed("Each item may appear only once per receipt")
        seen.add(r.item_id)
        outstanding = item.quantity - item.received_quantity
        if r.quantity > outstanding:
            raise ValidationFailed(f"Cannot receive {r.quantity} of {item.product.name}; only {outstanding} outstanding",
                                   code="over_receipt")
        completes = r.quantity == outstanding
        value = (item.line_total - item.received_value) if completes else q2(item.line_total * r.quantity / item.quantity)
        net_unit_cost = q2((item.unit_cost * item.quantity - item.discount_amount) / item.quantity)
        inventory_service.receive_stock(
            db, item.product, r.quantity, net_unit_cost, user=user, txn_type=InventoryTxnType.PURCHASE,
            batch_number=r.batch_number, manufacturing_date=r.manufacturing_date, expiry_date=r.expiry_date,
            supplier_id=po.supplier_id, goods_receipt_id=grn.id, reference_type="purchase", reference_id=po.id,
            reason=f"Received against {po.po_number}",
        )
        item.received_quantity += r.quantity
        item.received_value += value
        total_value += value
        _remember_cost(db, po.supplier_id, item.product, net_unit_cost, user)
    grn.value = total_value
    po.received_value += total_value
    po.status = (PurchaseStatus.RECEIVED.value if all(i.received_quantity >= i.quantity for i in po.items)
                 else PurchaseStatus.PARTIALLY_RECEIVED.value)
    ledger.post_supplier(db, po.supplier_id, LedgerType.PURCHASE.value, total_value, user=user, reference_type="purchase",
                         reference_id=po.id, reference_number=f"{po.po_number} / {grn.grn_number}",
                         notes=f"Goods received ({grn.grn_number})")
    audit.record(db, user=user, action="purchase.receive", entity="purchase", entity_id=po.id,
                 new={"grn": grn.grn_number, "value": total_value, "status": po.status})
    return grn


def _remember_cost(db: Session, supplier_id: int, product, cost: Decimal, user: User) -> None:  # noqa: ANN001
    sp = db.scalar(select(SupplierProduct).where(SupplierProduct.supplier_id == supplier_id,
                                                 SupplierProduct.product_id == product.id))
    if sp is None:
        db.add(SupplierProduct(supplier_id=supplier_id, product_id=product.id, last_cost=cost))
    else:
        sp.last_cost = cost
    if product.purchase_price != cost:
        old = product.purchase_price
        product.purchase_price = cost
        audit.record(db, user=user, action="product.cost_update", entity="product", entity_id=product.id,
                     old={"purchase_price": old}, new={"purchase_price": cost}, description="Updated from goods receipt")


def return_to_supplier(db: Session, data: PurchaseReturnCreate, user: User) -> PurchaseReturn:
    supplier = db.get(Supplier, data.supplier_id)
    if not supplier:
        raise ValidationFailed("Supplier not found")
    po = get_purchase(db, data.purchase_id) if data.purchase_id else None
    if po and po.supplier_id != supplier.id:
        raise ValidationFailed("Purchase order belongs to a different supplier")
    ret = PurchaseReturn(
        return_number=numbering.next_number(db, "PRET"),
        supplier_id=supplier.id, purchase_id=po.id if po else None, return_date=data.return_date or date.today(),
        reason=data.reason, created_by=user.id,
    )
    db.add(ret)
    db.flush()
    total = ZERO
    for line in data.items:
        product = catalog_service.get_product(db, line.product_id)
        batch = db.get(InventoryBatch, line.batch_id)
        if not batch or batch.product_id != product.id:
            raise ValidationFailed("Batch does not belong to that product")
        if batch.supplier_id and batch.supplier_id != supplier.id:
            raise ValidationFailed("That batch was not supplied by this supplier")
        item = None
        if po:
            item = next((i for i in po.items if i.product_id == product.id), None)
            if item is None:
                raise ValidationFailed(f"{product.name} is not on {po.po_number}")
            if line.quantity > item.received_quantity - item.returned_quantity:
                raise ValidationFailed(f"Cannot return more than was received of {product.name}")
        inventory_service.issue_stock(
            db, product, line.quantity, txn_type=InventoryTxnType.PURCHASE_RETURN, user=user, reference_type="purchase_return",
            reference_id=ret.id, reason=data.reason, batch_id=batch.id, allow_oversell=False, allow_expired=True)
        unit = q2(item.line_total / item.quantity) if item else Decimal(batch.purchase_cost)
        amount = q2(unit * line.quantity)
        if item:
            item.returned_quantity += line.quantity
        ret.items.append(PurchaseReturnItem(
            purchase_item_id=item.id if item else None, product_id=product.id, batch_id=batch.id,
            quantity=line.quantity, unit_cost=unit, amount=amount))
        total += amount
    ret.total_amount = total
    ledger.post_supplier(db, supplier.id, LedgerType.RETURN.value, -total, user=user, reference_type="purchase_return",
                         reference_id=ret.id, reference_number=ret.return_number, notes=data.reason)
    audit.record(db, user=user, action="purchase.return", entity="purchase_return", entity_id=ret.id,
                 new={"number": ret.return_number, "supplier": supplier.name, "total": total, "reason": data.reason})
    return ret
