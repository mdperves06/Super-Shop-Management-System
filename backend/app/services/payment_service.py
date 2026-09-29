"""Standalone money movements with suppliers and customers (not POS sale payments)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationFailed
from app.models.auth import User
from app.models.customers import Customer
from app.models.enums import CashTxnType, LedgerType
from app.models.finance import Payment, PaymentMethod
from app.models.purchasing import PurchaseOrder, Supplier
from app.schemas.purchasing import PaymentIn
from app.services import audit, cash_service, ledger, numbering
from app.services.pricing import q2


def active_method(db: Session, method_id: int, reference: str | None, transaction_id: str | None) -> PaymentMethod:
    method = db.get(PaymentMethod, method_id)
    if not method or not method.is_active:
        raise ValidationFailed("Payment method not found or inactive")
    if method.requires_reference and not (reference or transaction_id):
        raise ValidationFailed(f"{method.name} payments require a reference or transaction ID", code="reference_required")
    return method


def pay_supplier(db: Session, supplier: Supplier, data: PaymentIn, user: User) -> Payment:
    amount = q2(data.amount)
    method = active_method(db, data.payment_method_id, data.reference_number, data.transaction_id)
    if amount > supplier.balance:
        raise ValidationFailed(f"Payment exceeds the outstanding balance of ৳{supplier.balance:,.2f}", code="overpayment")
    po = None
    if data.purchase_id:
        po = db.get(PurchaseOrder, data.purchase_id)
        if not po or po.supplier_id != supplier.id:
            raise ValidationFailed("Purchase order not found for this supplier")
        po.paid_amount += amount
    pay = Payment(
        payment_number=numbering.next_number(db, "PAY"), direction="OUT", party_type="SUPPLIER", party_id=supplier.id,
        payment_method_id=method.id, amount=amount, reference_number=data.reference_number,
        transaction_id=data.transaction_id, purchase_id=data.purchase_id, notes=data.notes, user_id=user.id)
    db.add(pay)
    db.flush()
    ledger.post_supplier(db, supplier.id, LedgerType.PAYMENT.value, -amount, user=user, reference_type="payment",
                         reference_id=pay.id, reference_number=pay.payment_number, notes=data.notes or f"Paid via {method.name}")
    if method.method_type == "CASH":
        session = cash_service.get_open_session(db, user)
        if session:
            cash_service.record(db, session.id, CashTxnType.SUPPLIER_PAYMENT, -amount, user=user,
                                reference_type="payment", reference_id=pay.id, note=f"Supplier payment {supplier.name}")
    audit.record(db, user=user, action="supplier.payment", entity="supplier", entity_id=supplier.id,
                 new={"payment": pay.payment_number, "amount": amount, "method": method.name})
    return pay


def collect_from_customer(db: Session, customer: Customer, data: PaymentIn, user: User) -> Payment:
    amount = q2(data.amount)
    method = active_method(db, data.payment_method_id, data.reference_number, data.transaction_id)
    if amount > customer.balance:
        raise ValidationFailed(f"Payment exceeds the outstanding balance of ৳{customer.balance:,.2f}", code="overpayment")
    pay = Payment(
        payment_number=numbering.next_number(db, "RCV"), direction="IN", party_type="CUSTOMER", party_id=customer.id,
        payment_method_id=method.id, amount=amount, reference_number=data.reference_number,
        transaction_id=data.transaction_id, notes=data.notes, user_id=user.id)
    db.add(pay)
    db.flush()
    ledger.post_customer(db, customer.id, LedgerType.PAYMENT.value, -amount, user=user, reference_type="payment",
                         reference_id=pay.id, reference_number=pay.payment_number, notes=data.notes or f"Received via {method.name}")
    if method.method_type == "CASH":
        session = cash_service.get_open_session(db, user)
        if session:
            cash_service.record(db, session.id, CashTxnType.CUSTOMER_PAYMENT, amount, user=user,
                                reference_type="payment", reference_id=pay.id, note=f"Payment from {customer.name}")
    audit.record(db, user=user, action="customer.payment", entity="customer", entity_id=customer.id,
                 new={"payment": pay.payment_number, "amount": amount, "method": method.name})
    return pay


def list_payments(db: Session, party_type: str, party_id: int):  # noqa: ANN201
    return select(Payment).where(Payment.party_type == party_type, Payment.party_id == party_id).order_by(Payment.id.desc())


def to_dict(p: Payment) -> Payment:
    return p


def adjust_supplier_balance(db: Session, supplier: Supplier, amount: Decimal, reason: str, user: User) -> None:
    ledger.post_supplier(db, supplier.id, LedgerType.ADJUSTMENT.value, amount, user=user, notes=reason)
    audit.record(db, user=user, action="supplier.balance_adjust", entity="supplier", entity_id=supplier.id,
                 new={"amount": amount, "reason": reason})


def require_supplier(db: Session, supplier_id: int) -> Supplier:
    s = db.get(Supplier, supplier_id)
    if not s or s.is_deleted:
        raise NotFoundError("Supplier not found")
    return s
