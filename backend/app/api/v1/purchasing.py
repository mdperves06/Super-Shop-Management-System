from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Pagination, require
from app.core.errors import ConflictError
from app.models.auth import User
from app.models.base import utcnow
from app.models.enums import LedgerType
from app.models.finance import Payment
from app.models.purchasing import (
    GoodsReceipt,
    PurchaseOrder,
    PurchaseReturn,
    Supplier,
    SupplierTransaction,
)
from app.repositories.base import apply_sort, like, page_response, paginate
from app.schemas.common import Message, Page
from app.schemas.purchasing import (
    BalanceAdjustment,
    CancelIn,
    GoodsReceiptOut,
    LedgerRow,
    PaymentIn,
    PaymentOut,
    PurchaseCreate,
    PurchaseOut,
    PurchaseReturnCreate,
    PurchaseReturnOut,
    PurchaseUpdate,
    ReceiveIn,
    SupplierCreate,
    SupplierOut,
    SupplierProfile,
    SupplierUpdate,
)
from app.services import audit, ledger, numbering, payment_service, purchase_service, settings_service
from app.utils.dates import get_tz, range_bounds

router = APIRouter(tags=["purchasing"])


# ---- suppliers ------------------------------------------------------------------------

@router.get("/suppliers", response_model=Page[SupplierOut])
def list_suppliers(db: DB, p: Pagination, _: Annotated[User, Depends(require("supplier.read"))],
                   is_active: bool | None = None, has_balance: bool | None = None):
    stmt = select(Supplier).where(Supplier.is_deleted.is_(False))
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(Supplier.name.ilike(t, escape="\\"), Supplier.company.ilike(t, escape="\\"),
                              Supplier.phone.ilike(t, escape="\\"), Supplier.code.ilike(t, escape="\\")))
    if is_active is not None:
        stmt = stmt.where(Supplier.is_active == is_active)
    if has_balance:
        stmt = stmt.where(Supplier.balance > 0)
    stmt = apply_sort(stmt, Supplier, p.sort, {"name", "balance", "created_at", "code"}, Supplier.name)
    rows, total = paginate(db, stmt, p)
    return page_response([SupplierOut.model_validate(r) for r in rows], total, p)


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierCreate, request: Request, db: DB, user: Annotated[User, Depends(require("supplier.create"))]):
    if body.phone and db.scalar(select(Supplier.id).where(Supplier.phone == body.phone, Supplier.is_deleted.is_(False))):
        raise ConflictError("A supplier with this phone number already exists", code="duplicate_phone")
    data = body.model_dump(exclude={"opening_balance"})
    s = Supplier(code=numbering.next_number(db, "SUP", width=4), opening_balance=body.opening_balance, balance=0, **data)
    db.add(s)
    db.flush()
    if body.opening_balance:
        ledger.post_supplier(db, s.id, LedgerType.OPENING.value, body.opening_balance, user=user, notes="Opening balance")
    audit.record(db, user=user, action="supplier.create", entity="supplier", entity_id=s.id, new=data, request=request)
    db.commit()
    db.refresh(s)
    return s


def _get(db: DB, supplier_id: int) -> Supplier:
    return payment_service.require_supplier(db, supplier_id)


@router.get("/suppliers/{supplier_id}", response_model=SupplierProfile)
def supplier_profile(supplier_id: int, db: DB, _: Annotated[User, Depends(require("supplier.read"))]):
    s = _get(db, supplier_id)
    purchases = db.execute(select(func.coalesce(func.sum(PurchaseOrder.received_value), 0), func.count(PurchaseOrder.id))
                           .where(PurchaseOrder.supplier_id == s.id, PurchaseOrder.status != "CANCELLED")).one()
    paid = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.party_type == "SUPPLIER", Payment.party_id == s.id)) or 0
    returns = db.scalar(select(func.coalesce(func.sum(PurchaseReturn.total_amount), 0)).where(PurchaseReturn.supplier_id == s.id)) or 0
    out = SupplierProfile.model_validate({**SupplierOut.model_validate(s).model_dump(), "total_purchases": purchases[0],
                                          "total_paid": paid, "total_returns": returns, "purchase_count": purchases[1]})
    return out


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, body: SupplierUpdate, request: Request, db: DB, user: Annotated[User, Depends(require("supplier.update"))]):
    s = _get(db, supplier_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("phone") and db.scalar(select(Supplier.id).where(Supplier.phone == changes["phone"], Supplier.id != s.id, Supplier.is_deleted.is_(False))):
        raise ConflictError("A supplier with this phone number already exists", code="duplicate_phone")
    old = {k: getattr(s, k) for k in changes}
    for k, v in changes.items():
        setattr(s, k, v)
    audit.record(db, user=user, action="supplier.update", entity="supplier", entity_id=s.id, old=old, new=changes, request=request)
    db.commit()
    return s


@router.delete("/suppliers/{supplier_id}", response_model=Message)
def delete_supplier(supplier_id: int, request: Request, db: DB, user: Annotated[User, Depends(require("supplier.delete"))]):
    s = _get(db, supplier_id)
    if s.balance != 0:
        raise ConflictError("Supplier has an outstanding balance; settle it first", code="supplier_has_balance")
    s.is_deleted, s.is_active, s.deleted_at = True, False, utcnow()
    audit.record(db, user=user, action="supplier.delete", entity="supplier", entity_id=s.id, request=request)
    db.commit()
    return Message(message="Supplier deleted")


@router.get("/suppliers/{supplier_id}/ledger", response_model=Page[LedgerRow])
def supplier_ledger(supplier_id: int, db: DB, p: Pagination, _: Annotated[User, Depends(require("supplier.read"))],
                    start: date | None = None, end: date | None = None):
    s = _get(db, supplier_id)
    stmt = select(SupplierTransaction).where(SupplierTransaction.supplier_id == s.id)
    if start and end:
        lo, hi = range_bounds(start, end, get_tz(settings_service.get(db, "locale.timezone")))
        stmt = stmt.where(SupplierTransaction.created_at >= lo, SupplierTransaction.created_at < hi)
    rows, total = paginate(db, stmt.order_by(SupplierTransaction.id.desc()), p)
    users = _user_names(db, {r.user_id for r in rows})
    return page_response([LedgerRow(**_ledger_dict(r, users)) for r in rows], total, p)


def _user_names(db: DB, ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all()) if ids else {}


def _ledger_dict(r, users: dict[int, str]) -> dict:  # noqa: ANN001
    return {"id": r.id, "created_at": r.created_at, "txn_type": r.txn_type, "amount": r.amount, "balance_after": r.balance_after,
            "reference_type": r.reference_type, "reference_id": r.reference_id, "reference_number": r.reference_number,
            "notes": r.notes, "user_name": users.get(r.user_id)}


@router.post("/suppliers/{supplier_id}/payments", response_model=PaymentOut, status_code=201)
def pay_supplier(supplier_id: int, body: PaymentIn, request: Request, db: DB, user: Annotated[User, Depends(require("supplier.payment"))]):
    s = _get(db, supplier_id)
    pay = payment_service.pay_supplier(db, s, body, user)
    db.commit()
    out = PaymentOut.model_validate(pay)
    out.method_name = pay.payment_method.name
    return out


@router.get("/suppliers/{supplier_id}/payments", response_model=Page[PaymentOut])
def supplier_payments(supplier_id: int, db: DB, p: Pagination, _: Annotated[User, Depends(require("supplier.read"))]):
    s = _get(db, supplier_id)
    rows, total = paginate(db, payment_service.list_payments(db, "SUPPLIER", s.id), p)
    items = []
    for r in rows:
        o = PaymentOut.model_validate(r)
        o.method_name = r.payment_method.name
        items.append(o)
    return page_response(items, total, p)


@router.post("/suppliers/{supplier_id}/adjustments", response_model=SupplierOut)
def adjust_supplier(supplier_id: int, body: BalanceAdjustment, db: DB, user: Annotated[User, Depends(require("supplier.update", "supplier.payment"))]):
    s = _get(db, supplier_id)
    payment_service.adjust_supplier_balance(db, s, body.amount, body.reason, user)
    db.commit()
    db.refresh(s)
    return s


# ---- purchase orders ------------------------------------------------------------------

def _po_out(po: PurchaseOrder) -> PurchaseOut:
    out = PurchaseOut.model_validate(po)
    out.supplier_name = po.supplier.name
    for item_out, item in zip(out.items, po.items):
        item_out.product_name, item_out.sku, item_out.track_expiry = item.product.name, item.product.sku, item.product.track_expiry
    return out


@router.get("/purchases", response_model=Page[PurchaseOut])
def list_purchases(db: DB, p: Pagination, _: Annotated[User, Depends(require("purchase.read"))], status: str | None = None,
                   supplier_id: int | None = None, start: date | None = None, end: date | None = None):
    stmt = select(PurchaseOrder).join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    if start:
        stmt = stmt.where(PurchaseOrder.order_date >= start)
    if end:
        stmt = stmt.where(PurchaseOrder.order_date <= end)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(PurchaseOrder.po_number.ilike(t, escape="\\"), Supplier.name.ilike(t, escape="\\")))
    stmt = apply_sort(stmt, PurchaseOrder, p.sort, {"po_number", "order_date", "total_amount", "status"}, PurchaseOrder.id.desc())
    rows, total = paginate(db, stmt, p)
    return page_response([_po_out(r) for r in rows], total, p)


@router.post("/purchases", response_model=PurchaseOut, status_code=201)
def create_purchase(body: PurchaseCreate, db: DB, user: Annotated[User, Depends(require("purchase.create"))]):
    po = purchase_service.create_purchase(db, body, user)
    db.commit()
    return _po_out(po)


@router.get("/purchases/{purchase_id}", response_model=PurchaseOut)
def get_purchase(purchase_id: int, db: DB, _: Annotated[User, Depends(require("purchase.read"))]):
    return _po_out(purchase_service.get_purchase(db, purchase_id))


@router.put("/purchases/{purchase_id}", response_model=PurchaseOut)
def update_purchase(purchase_id: int, body: PurchaseUpdate, db: DB, user: Annotated[User, Depends(require("purchase.create"))]):
    po = purchase_service.update_purchase(db, purchase_service.get_purchase(db, purchase_id, lock=True), body, user)
    db.commit()
    return _po_out(po)


@router.post("/purchases/{purchase_id}/submit", response_model=PurchaseOut)
def submit_purchase(purchase_id: int, db: DB, user: Annotated[User, Depends(require("purchase.create"))]):
    po = purchase_service.submit(db, purchase_service.get_purchase(db, purchase_id, lock=True), user)
    db.commit()
    return _po_out(po)


@router.post("/purchases/{purchase_id}/approve", response_model=PurchaseOut)
def approve_purchase(purchase_id: int, db: DB, user: Annotated[User, Depends(require("purchase.approve"))]):
    po = purchase_service.approve(db, purchase_service.get_purchase(db, purchase_id, lock=True), user)
    db.commit()
    return _po_out(po)


@router.post("/purchases/{purchase_id}/cancel", response_model=PurchaseOut)
def cancel_purchase(purchase_id: int, body: CancelIn, db: DB, user: Annotated[User, Depends(require("purchase.cancel"))]):
    po = purchase_service.cancel(db, purchase_service.get_purchase(db, purchase_id, lock=True), body.reason, user)
    db.commit()
    return _po_out(po)


@router.post("/purchases/{purchase_id}/receive", response_model=PurchaseOut)
def receive_purchase(purchase_id: int, body: ReceiveIn, db: DB, user: Annotated[User, Depends(require("purchase.receive"))]):
    po = purchase_service.get_purchase(db, purchase_id, lock=True)
    purchase_service.receive(db, po, body, user)
    db.commit()
    db.refresh(po)
    return _po_out(po)


@router.get("/goods-receipts", response_model=Page[GoodsReceiptOut])
def goods_receipts(db: DB, p: Pagination, _: Annotated[User, Depends(require("purchase.read"))], purchase_id: int | None = None):
    stmt = select(GoodsReceipt).join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_id)
    if purchase_id:
        stmt = stmt.where(GoodsReceipt.purchase_id == purchase_id)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(GoodsReceipt.grn_number.ilike(t, escape="\\"), PurchaseOrder.po_number.ilike(t, escape="\\")))
    rows, total = paginate(db, stmt.order_by(GoodsReceipt.id.desc()), p)
    pos = {po.id: po for po in db.scalars(select(PurchaseOrder).where(PurchaseOrder.id.in_({r.purchase_id for r in rows})))} if rows else {}
    users = _user_names(db, {r.received_by for r in rows})
    items = []
    for r in rows:
        o = GoodsReceiptOut.model_validate(r)
        o.po_number, o.supplier_name, o.received_by_name = pos[r.purchase_id].po_number, pos[r.purchase_id].supplier.name, users.get(r.received_by)
        items.append(o)
    return page_response(items, total, p)


# ---- purchase returns -----------------------------------------------------------------

def _ret_out(r: PurchaseReturn) -> PurchaseReturnOut:
    out = PurchaseReturnOut.model_validate(r)
    out.supplier_name = r.supplier.name
    for io, i in zip(out.items, r.items):
        io.product_name = i.product.name
    return out


@router.get("/purchase-returns", response_model=Page[PurchaseReturnOut])
def list_purchase_returns(db: DB, p: Pagination, _: Annotated[User, Depends(require("purchase.read"))], supplier_id: int | None = None):
    stmt = select(PurchaseReturn).join(Supplier, Supplier.id == PurchaseReturn.supplier_id)
    if supplier_id:
        stmt = stmt.where(PurchaseReturn.supplier_id == supplier_id)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(PurchaseReturn.return_number.ilike(t, escape="\\"), Supplier.name.ilike(t, escape="\\")))
    rows, total = paginate(db, stmt.order_by(PurchaseReturn.id.desc()), p)
    return page_response([_ret_out(r) for r in rows], total, p)


@router.post("/purchase-returns", response_model=PurchaseReturnOut, status_code=201)
def create_purchase_return(body: PurchaseReturnCreate, db: DB, user: Annotated[User, Depends(require("purchase.return"))]):
    ret = purchase_service.return_to_supplier(db, body, user)
    db.commit()
    return _ret_out(ret)
