from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Money, SoftDeleteMixin, TimestampMixin, utcnow


class PaymentMethod(Base, TimestampMixin):
    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    method_type: Mapped[str] = mapped_column(String(15), default="OTHER")
    requires_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Payment(Base):
    """Standalone payments: customer collections (IN) and supplier payments (OUT)."""

    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_party", "party_type", "party_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_number: Mapped[str] = mapped_column(String(30), unique=True)
    direction: Mapped[str] = mapped_column(String(3))  # IN | OUT
    party_type: Mapped[str] = mapped_column(String(15))  # CUSTOMER | SUPPLIER
    party_id: Mapped[int] = mapped_column()
    payment_method_id: Mapped[int] = mapped_column(ForeignKey("payment_methods.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    reference_number: Mapped[str | None] = mapped_column(String(80))
    transaction_id: Mapped[str | None] = mapped_column(String(80))
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    payment_method: Mapped[PaymentMethod] = relationship(lazy="joined")


class ExpenseCategory(Base, TimestampMixin):
    __tablename__ = "expense_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Expense(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_number: Mapped[str] = mapped_column(String(30), unique=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("expense_categories.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    description: Mapped[str | None] = mapped_column(Text)
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    payment_method_id: Mapped[int] = mapped_column(ForeignKey("payment_methods.id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    attachment_path: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")  # ACTIVE | VOID
    void_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    category: Mapped[ExpenseCategory] = relationship(lazy="joined")
    payment_method: Mapped[PaymentMethod] = relationship(lazy="joined")


class CashRegister(Base, TimestampMixin):
    __tablename__ = "cash_registers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    location: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CashRegisterSession(Base):
    __tablename__ = "cash_register_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    register_id: Mapped[int] = mapped_column(ForeignKey("cash_registers.id"), index=True)
    opened_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    opening_cash: Mapped[Decimal] = mapped_column(Money, default=0)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    expected_cash: Mapped[Decimal | None] = mapped_column(Money)
    actual_cash: Mapped[Decimal | None] = mapped_column(Money)
    difference: Mapped[Decimal | None] = mapped_column(Money)
    discrepancy_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="OPEN", index=True)

    register: Mapped[CashRegister] = relationship(lazy="joined")
    opener: Mapped["User"] = relationship(foreign_keys=[opened_by], lazy="joined")  # noqa: F821


class CashTransaction(Base):
    """Signed cash movements inside a session; expected cash = sum(amount)."""

    __tablename__ = "cash_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("cash_register_sessions.id"), index=True)
    txn_type: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Money)
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[int | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(255))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
