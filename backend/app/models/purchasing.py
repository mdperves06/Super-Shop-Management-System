from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Money, Qty, Rate, SoftDeleteMixin, TimestampMixin, utcnow


class Supplier(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    company: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    contact_person: Mapped[str | None] = mapped_column(String(150))
    tax_id: Mapped[str | None] = mapped_column(String(50))  # BIN / TIN
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=0)
    balance: Mapped[Decimal] = mapped_column(Money, default=0)  # payable: what we owe the supplier
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SupplierProduct(Base, TimestampMixin):
    __tablename__ = "supplier_products"
    __table_args__ = (UniqueConstraint("supplier_id", "product_id", name="uq_supplier_product"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    supplier_sku: Mapped[str | None] = mapped_column(String(60))
    last_cost: Mapped[Decimal] = mapped_column(Money, default=0)


class SupplierTransaction(Base):
    """Supplier ledger. Positive amount = payable increases (we owe more)."""

    __tablename__ = "supplier_transactions"
    __table_args__ = (Index("ix_suppl_txn", "supplier_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    txn_type: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Money)
    balance_after: Mapped[Decimal] = mapped_column(Money)
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[int | None] = mapped_column()
    reference_number: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(30), unique=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(25), default="DRAFT", index=True)
    order_date: Mapped[date] = mapped_column(Date)
    expected_date: Mapped[date | None] = mapped_column(Date)
    subtotal: Mapped[Decimal] = mapped_column(Money, default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    total_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    received_value: Mapped[Decimal] = mapped_column(Money, default=0)  # payable recognised so far
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_reason: Mapped[str | None] = mapped_column(Text)

    supplier: Mapped[Supplier] = relationship(lazy="joined")
    items: Mapped[list["PurchaseItem"]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan", lazy="selectin", order_by="PurchaseItem.id"
    )


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    received_quantity: Mapped[Decimal] = mapped_column(Qty, default=0)
    returned_quantity: Mapped[Decimal] = mapped_column(Qty, default=0)
    received_value: Mapped[Decimal] = mapped_column(Money, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Money)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Rate, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    line_total: Mapped[Decimal] = mapped_column(Money, default=0)

    purchase: Mapped[PurchaseOrder] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(lazy="joined")  # noqa: F821


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    grn_number: Mapped[str] = mapped_column(String(30), unique=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    value: Mapped[Decimal] = mapped_column(Money, default=0)
    notes: Mapped[str | None] = mapped_column(Text)


class PurchaseReturn(Base, TimestampMixin):
    __tablename__ = "purchase_returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_number: Mapped[str] = mapped_column(String(30), unique=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"))
    return_date: Mapped[date] = mapped_column(Date)
    total_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    supplier: Mapped[Supplier] = relationship(lazy="joined")
    items: Mapped[list["PurchaseReturnItem"]] = relationship(
        back_populates="purchase_return", cascade="all, delete-orphan", lazy="selectin"
    )


class PurchaseReturnItem(Base):
    __tablename__ = "purchase_return_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("purchase_returns.id", ondelete="CASCADE"), index=True)
    purchase_item_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_items.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_batches.id"))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    unit_cost: Mapped[Decimal] = mapped_column(Money)
    amount: Mapped[Decimal] = mapped_column(Money)

    purchase_return: Mapped[PurchaseReturn] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(lazy="joined")  # noqa: F821
