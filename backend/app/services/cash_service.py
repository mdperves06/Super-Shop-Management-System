from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models.auth import User
from app.models.base import utcnow
from app.models.enums import CashTxnType
from app.models.finance import CashRegister, CashRegisterSession, CashTransaction
from app.services import audit, notification_service
from app.services.pricing import q2

ZERO = Decimal("0")


def get_open_session(db: Session, user: User) -> CashRegisterSession | None:
    return db.scalar(select(CashRegisterSession).where(
        CashRegisterSession.opened_by == user.id, CashRegisterSession.status == "OPEN"))


def open_session(db: Session, user: User, register_id: int, opening_cash: Decimal) -> CashRegisterSession:
    opening_cash = q2(opening_cash)
    if opening_cash < 0:
        raise ValidationFailed("Opening cash cannot be negative")
    register = db.get(CashRegister, register_id)
    if not register or not register.is_active:
        raise NotFoundError("Cash register not found")
    if get_open_session(db, user):
        raise ConflictError("You already have an open register session", code="session_already_open")
    if db.scalar(select(CashRegisterSession.id).where(
            CashRegisterSession.register_id == register_id, CashRegisterSession.status == "OPEN")):
        raise ConflictError("This register is already open by another user", code="register_in_use")
    session = CashRegisterSession(register_id=register_id, opened_by=user.id, opening_cash=opening_cash, status="OPEN")
    db.add(session)
    db.flush()
    record(db, session.id, CashTxnType.OPENING, opening_cash, user=user, note="Opening cash")
    audit.record(db, user=user, action="register.open", entity="cash_session", entity_id=session.id,
                 new={"register": register.name, "opening_cash": opening_cash})
    return session


def record(db: Session, session_id: int, txn_type: CashTxnType, amount: Decimal, *, user: User | None,
           reference_type: str | None = None, reference_id: int | None = None, note: str | None = None) -> CashTransaction:
    row = CashTransaction(session_id=session_id, txn_type=txn_type.value, amount=q2(amount), reference_type=reference_type,
                          reference_id=reference_id, note=note, user_id=user.id if user else None)
    db.add(row)
    return row


def expected_cash(db: Session, session_id: int) -> Decimal:
    return Decimal(str(db.scalar(select(func.coalesce(func.sum(CashTransaction.amount), 0)).where(
        CashTransaction.session_id == session_id)) or 0))


def breakdown(db: Session, session_id: int) -> dict[str, Decimal]:
    rows = db.execute(select(CashTransaction.txn_type, func.sum(CashTransaction.amount))
                      .where(CashTransaction.session_id == session_id).group_by(CashTransaction.txn_type)).all()
    return {t: Decimal(str(v)) for t, v in rows}


def close_session(db: Session, session: CashRegisterSession, user: User, actual_cash: Decimal, reason: str | None) -> CashRegisterSession:
    if session.status != "OPEN":
        raise ConflictError("This session is already closed")
    actual = q2(actual_cash)
    if actual < 0:
        raise ValidationFailed("Actual cash cannot be negative")
    expected = expected_cash(db, session.id)
    diff = actual - expected
    reason = (reason or "").strip()
    if diff != 0 and len(reason) < 3:
        raise ValidationFailed("A reason is required when the counted cash differs from the expected cash",
                               code="discrepancy_reason_required",
                               details={"expected": float(expected), "actual": float(actual), "difference": float(diff)})
    session.expected_cash, session.actual_cash, session.difference = expected, actual, diff
    session.discrepancy_reason = reason or None
    session.closed_by, session.closed_at, session.status = user.id, utcnow(), "CLOSED"
    audit.record(db, user=user, action="register.close", entity="cash_session", entity_id=session.id,
                 new={"expected": expected, "actual": actual, "difference": diff, "reason": reason or None},
                 description="Cash discrepancy" if diff != 0 else None)
    if diff != 0:
        notification_service.notify(
            db, type="cash_discrepancy", severity="warning" if abs(diff) < 1000 else "critical",
            title="Cash register discrepancy",
            message=f"Session #{session.id} closed with a difference of ৳{diff:,.2f} (expected ৳{expected:,.2f}, counted ৳{actual:,.2f}). Reason: {reason}",
            permission="register.manage", entity="cash_session", entity_id=session.id, dedupe_key=f"cashdiff:{session.id}")
    return session
