from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Pagination, require
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models.auth import User
from app.models.base import utcnow
from app.models.customers import Customer, CustomerAddress, CustomerTransaction
from app.models.enums import LedgerType
from app.models.finance import Payment
from app.models.sales import Sale, SaleReturn
from app.repositories.base import apply_sort, like, page_response, paginate
from app.schemas.common import Message, Page
from app.schemas.customers import (
    AddressIn,
    AddressOut,
    CustomerCreate,
    CustomerOut,
    CustomerProfile,
    CustomerUpdate,
)
from app.schemas.purchasing import BalanceAdjustment, LedgerRow, PaymentIn, PaymentOut
from app.services import audit, ledger, numbering, payment_service, settings_service
from app.utils.dates import get_tz, range_bounds

router = APIRouter(prefix="/customers", tags=["customers"])
Reader = Annotated[User, Depends(require("customer.read", "sale.create", any_of=True))]


def get_customer(db: DB, customer_id: int) -> Customer:
    c = db.get(Customer, customer_id)
    if not c or c.is_deleted:
        raise NotFoundError("Customer not found")
    return c


@router.get("", response_model=Page[CustomerOut])
def list_customers(db: DB, p: Pagination, _: Reader, is_active: bool | None = None, has_balance: bool | None = None,
                   customer_type: str | None = None):
    stmt = select(Customer).where(Customer.is_deleted.is_(False))
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(Customer.name.ilike(t, escape="\\"), Customer.phone.ilike(t, escape="\\"),
                              Customer.code.ilike(t, escape="\\"), Customer.email.ilike(t, escape="\\")))
    if is_active is not None:
        stmt = stmt.where(Customer.is_active == is_active)
    if has_balance:
        stmt = stmt.where(Customer.balance > 0)
    if customer_type:
        stmt = stmt.where(Customer.customer_type == customer_type)
    stmt = apply_sort(stmt, Customer, p.sort, {"name", "balance", "created_at", "code", "loyalty_points"}, Customer.name)
    rows, total = paginate(db, stmt, p)
    return page_response([CustomerOut.model_validate(r) for r in rows], total, p)


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerCreate, request: Request, db: DB, user: Annotated[User, Depends(require("customer.create"))]):
    if body.phone and db.scalar(select(Customer.id).where(Customer.phone == body.phone)):
        raise ConflictError("A customer with this phone number already exists", code="duplicate_phone")
    data = body.model_dump(exclude={"opening_balance"})
    c = Customer(code=numbering.next_number(db, "CUS", width=5), opening_balance=body.opening_balance, balance=0, **data)
    db.add(c)
    db.flush()
    if body.opening_balance:
        ledger.post_customer(db, c.id, LedgerType.OPENING.value, body.opening_balance, user=user, notes="Opening balance")
    audit.record(db, user=user, action="customer.create", entity="customer", entity_id=c.id, new=data, request=request)
    db.commit()
    db.refresh(c)
    return c


@router.get("/{customer_id}", response_model=CustomerProfile)
def customer_profile(customer_id: int, db: DB, _: Reader):
    c = get_customer(db, customer_id)
    sales = db.execute(select(func.coalesce(func.sum(Sale.total_amount), 0), func.count(Sale.id), func.max(Sale.sale_date))
                       .where(Sale.customer_id == c.id, Sale.status == "COMPLETED")).one()
    rets = db.scalar(select(func.coalesce(func.sum(SaleReturn.total_amount), 0)).where(SaleReturn.customer_id == c.id)) or 0
    paid = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.party_type == "CUSTOMER", Payment.party_id == c.id)) or 0
    return CustomerProfile.model_validate({**CustomerOut.model_validate(c).model_dump(), "total_purchases": sales[0], "sale_count": sales[1],
                                           "last_purchase_at": sales[2], "total_returns": rets, "total_paid": paid})


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, body: CustomerUpdate, request: Request, db: DB, user: Annotated[User, Depends(require("customer.update"))]):
    c = get_customer(db, customer_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("phone") and db.scalar(select(Customer.id).where(Customer.phone == changes["phone"], Customer.id != c.id)):
        raise ConflictError("A customer with this phone number already exists", code="duplicate_phone")
    old = {k: getattr(c, k) for k in changes}
    for k, v in changes.items():
        setattr(c, k, v)
    audit.record(db, user=user, action="customer.update", entity="customer", entity_id=c.id, old=old, new=changes, request=request)
    db.commit()
    return c


@router.delete("/{customer_id}", response_model=Message)
def delete_customer(customer_id: int, request: Request, db: DB, user: Annotated[User, Depends(require("customer.delete"))]):
    c = get_customer(db, customer_id)
    if c.balance != 0:
        raise ConflictError("Customer has an outstanding balance", code="customer_has_balance")
    c.is_deleted, c.is_active, c.deleted_at = True, False, utcnow()
    if c.phone:
        c.phone = None  # free the number; history stays linked through the customer id
    audit.record(db, user=user, action="customer.delete", entity="customer", entity_id=c.id, request=request)
    db.commit()
    return Message(message="Customer deleted")


@router.post("/{customer_id}/addresses", response_model=AddressOut, status_code=201)
def add_address(customer_id: int, body: AddressIn, db: DB, _: Annotated[User, Depends(require("customer.update"))]):
    c = get_customer(db, customer_id)
    if body.is_default:
        for a in c.addresses:
            a.is_default = False
    row = CustomerAddress(customer_id=c.id, **body.model_dump())
    c.addresses.append(row)
    db.commit()
    return row


@router.delete("/{customer_id}/addresses/{address_id}", response_model=Message)
def delete_address(customer_id: int, address_id: int, db: DB, _: Annotated[User, Depends(require("customer.update"))]):
    c = get_customer(db, customer_id)
    row = next((a for a in c.addresses if a.id == address_id), None)
    if not row:
        raise NotFoundError("Address not found")
    c.addresses.remove(row)
    db.commit()
    return Message(message="Address removed")


@router.get("/{customer_id}/ledger", response_model=Page[LedgerRow])
def customer_ledger(customer_id: int, db: DB, p: Pagination, _: Annotated[User, Depends(require("customer.read"))],
                    start: date | None = None, end: date | None = None):
    c = get_customer(db, customer_id)
    stmt = select(CustomerTransaction).where(CustomerTransaction.customer_id == c.id)
    if start and end:
        lo, hi = range_bounds(start, end, get_tz(settings_service.get(db, "locale.timezone")))
        stmt = stmt.where(CustomerTransaction.created_at >= lo, CustomerTransaction.created_at < hi)
    rows, total = paginate(db, stmt.order_by(CustomerTransaction.id.desc()), p)
    ids = {r.user_id for r in rows if r.user_id}
    users = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all()) if ids else {}
    return page_response([LedgerRow(id=r.id, created_at=r.created_at, txn_type=r.txn_type, amount=r.amount, balance_after=r.balance_after,
                                    reference_type=r.reference_type, reference_id=r.reference_id, reference_number=r.reference_number,
                                    notes=r.notes, user_name=users.get(r.user_id)) for r in rows], total, p)


@router.post("/{customer_id}/payments", response_model=PaymentOut, status_code=201)
def receive_payment(customer_id: int, body: PaymentIn, db: DB, user: Annotated[User, Depends(require("customer.payment"))]):
    c = get_customer(db, customer_id)
    pay = payment_service.collect_from_customer(db, c, body, user)
    db.commit()
    out = PaymentOut.model_validate(pay)
    out.method_name = pay.payment_method.name
    return out


@router.get("/{customer_id}/payments", response_model=Page[PaymentOut])
def customer_payments(customer_id: int, db: DB, p: Pagination, _: Annotated[User, Depends(require("customer.read"))]):
    c = get_customer(db, customer_id)
    rows, total = paginate(db, payment_service.list_payments(db, "CUSTOMER", c.id), p)
    items = []
    for r in rows:
        o = PaymentOut.model_validate(r)
        o.method_name = r.payment_method.name
        items.append(o)
    return page_response(items, total, p)


@router.post("/{customer_id}/adjustments", response_model=CustomerOut)
def adjust_customer_balance(customer_id: int, body: BalanceAdjustment, db: DB, user: Annotated[User, Depends(require("customer.update", "customer.payment"))]):
    c = get_customer(db, customer_id)
    ledger.post_customer(db, c.id, LedgerType.ADJUSTMENT.value, body.amount, user=user, notes=body.reason)
    audit.record(db, user=user, action="customer.balance_adjust", entity="customer", entity_id=c.id,
                 new={"amount": body.amount, "reason": body.reason})
    db.commit()
    db.refresh(c)
    return c
