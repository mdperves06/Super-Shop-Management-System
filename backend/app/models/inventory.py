from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Money, Qty, TimestampMixin, utcnow


class Inventory(Base, TimestampMixin):
    """One row per product. `current_stock` is the sellable quantity (sum of batch remainders)."""

    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), unique=True)
    current_stock: Mapped[Decimal] = mapped_column(Qty, default=0)
    reserved_stock: Mapped[Decimal] = mapped_column(Qty, default=0)
    damaged_stock: Mapped[Decimal] = mapped_column(Qty, default=0)
    expired_stock: Mapped[Decimal] = mapped_column(Qty, default=0)

    product: Mapped["Product"] = relationship(back_populates="inventory")  # noqa: F821

    @property
    def available_stock(self) -> Decimal:
        return self.current_stock - self.reserved_stock


class InventoryBatch(Base, TimestampMixin):
    __tablename__ = "inventory_batches"
    __table_args__ = (
        CheckConstraint("quantity_remaining >= 0 OR quantity_remaining IS NULL", name="ck_batch_non_negative"),
        Index("ix_batches_fefo", "product_id", "expiry_date", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_number: Mapped[str] = mapped_column(String(60), index=True)
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    purchase_cost: Mapped[Decimal] = mapped_column(Money, default=0)
    quantity_received: Mapped[Decimal] = mapped_column(Qty)
    quantity_remaining: Mapped[Decimal] = mapped_column(Qty)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    goods_receipt_id: Mapped[int | None] = mapped_column(ForeignKey("goods_receipts.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    product: Mapped["Product"] = relationship(lazy="joined")  # noqa: F821


class InventoryTransaction(Base):
    """Immutable stock ledger. Every stock movement writes exactly one row per batch touched."""

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        Index("ix_invtxn_product_date", "product_id", "created_at"),
        Index("ix_invtxn_ref", "reference_type", "reference_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_batches.id"))
    txn_type: Mapped[str] = mapped_column(String(30), index=True)
    quantity: Mapped[Decimal] = mapped_column(Qty)  # signed: + increases sellable stock
    balance_after: Mapped[Decimal] = mapped_column(Qty)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=0)
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[int | None] = mapped_column()
    reason: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    product: Mapped["Product"] = relationship(lazy="joined")  # noqa: F821


class StockAdjustment(Base):
    __tablename__ = "stock_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    adjustment_number: Mapped[str] = mapped_column(String(30), unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_batches.id"))
    adjustment_type: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    reason: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    product: Mapped["Product"] = relationship(lazy="joined")  # noqa: F821
