from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Money, Rate, SoftDeleteMixin, TimestampMixin, utcnow


class Customer(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    phone: Mapped[str | None] = mapped_column(String(30), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    customer_type: Mapped[str] = mapped_column(String(20), default="RETAIL")  # RETAIL | WHOLESALE | VIP
    loyalty_points: Mapped[int] = mapped_column(Integer, default=0)
    discount_percent: Mapped[Decimal] = mapped_column(Rate, default=0)
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=0)
    balance: Mapped[Decimal] = mapped_column(Money, default=0)  # receivable: what the customer owes us
    credit_limit: Mapped[Decimal] = mapped_column(Money, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    addresses: Mapped[list["CustomerAddress"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", lazy="selectin"
    )


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(50), default="Home")
    address: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped[Customer] = relationship(back_populates="addresses")


class CustomerTransaction(Base):
    """Customer ledger. Positive amount = receivable increases (customer owes more)."""

    __tablename__ = "customer_transactions"
    __table_args__ = (Index("ix_cust_txn", "customer_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    txn_type: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Money)
    balance_after: Mapped[Decimal] = mapped_column(Money)
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[int | None] = mapped_column()
    reference_number: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
