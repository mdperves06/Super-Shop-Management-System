"""Supplier and customer ledgers. Balances only change through these functions, one ledger row per change."""

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.auth import User
from app.models.customers import Customer, CustomerTransaction
from app.models.purchasing import Supplier, SupplierTransaction
from app.services.pricing import q2


def post_supplier(
    db: Session, supplier_id: int, txn_type: str, delta: Decimal, *, user: User | None,
    reference_type: str | None = None, reference_id: int | None = None, reference_number: str | None = None,
    notes: str | None = None,
) -> SupplierTransaction:
    """`delta` > 0 increases what we owe the supplier; < 0 reduces it."""
    delta = q2(delta)
    db.execute(select(Supplier.id).where(Supplier.id == supplier_id).with_for_update())
    res = db.execute(update(Supplier).where(Supplier.id == supplier_id).values(balance=Supplier.balance + delta),
                     execution_options={"synchronize_session": False})
    if res.rowcount != 1:
        raise NotFoundError("Supplier not found")
    balance = db.scalar(select(Supplier.balance).where(Supplier.id == supplier_id))
    for obj in list(db.identity_map.values()):
        if isinstance(obj, Supplier) and obj.id == supplier_id:
            db.expire(obj, ["balance"])
    row = SupplierTransaction(
        supplier_id=supplier_id, txn_type=txn_type, amount=delta, balance_after=balance, reference_type=reference_type,
        reference_id=reference_id, reference_number=reference_number, notes=notes, user_id=user.id if user else None,
    )
    db.add(row)
    return row


def post_customer(
    db: Session, customer_id: int, txn_type: str, delta: Decimal, *, user: User | None,
    reference_type: str | None = None, reference_id: int | None = None, reference_number: str | None = None,
    notes: str | None = None,
) -> CustomerTransaction:
    """`delta` > 0 increases what the customer owes us; < 0 reduces it."""
    delta = q2(delta)
    db.execute(select(Customer.id).where(Customer.id == customer_id).with_for_update())
    res = db.execute(update(Customer).where(Customer.id == customer_id).values(balance=Customer.balance + delta),
                     execution_options={"synchronize_session": False})
    if res.rowcount != 1:
        raise NotFoundError("Customer not found")
    balance = db.scalar(select(Customer.balance).where(Customer.id == customer_id))
    for obj in list(db.identity_map.values()):
        if isinstance(obj, Customer) and obj.id == customer_id:
            db.expire(obj, ["balance"])
    row = CustomerTransaction(
        customer_id=customer_id, txn_type=txn_type, amount=delta, balance_after=balance, reference_type=reference_type,
        reference_id=reference_id, reference_number=reference_number, notes=notes, user_id=user.id if user else None,
    )
    db.add(row)
    return row
