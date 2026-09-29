from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Money, Qty, Rate, TimestampMixin, utcnow


class Sale(Base, TimestampMixin):
    __tablename__ = "sales"
    __table_args__ = (Index("ix_sales_date_status", "sale_date", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(30), unique=True)
    sale_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    cashier_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("cash_register_sessions.id"))
    status: Mapped[str] = mapped_column(String(15), default="COMPLETED", index=True)
    return_status: Mapped[str] = mapped_column(String(10), default="NONE")
    subtotal: Mapped[Decimal] = mapped_column(Money, default=0)  # gross, before any discount
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    total_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    cogs_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    due_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    tendered_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    change_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    returned_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    void_reason: Mapped[str | None] = mapped_column(Text)
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)

    customer: Mapped["Customer | None"] = relationship(lazy="joined")  # noqa: F821
    cashier: Mapped["User"] = relationship(foreign_keys=[cashier_id], lazy="joined")  # noqa: F821
    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", lazy="selectin", order_by="SaleItem.id"
    )
    payments: Mapped[list["SalePayment"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", lazy="selectin", order_by="SalePayment.id"
    )


class SaleItem(Base):
    __tablename__ = "sale_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_sale_item_qty"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(60))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    returned_quantity: Mapped[Decimal] = mapped_column(Qty, default=0)
    unit_price: Mapped[Decimal] = mapped_column(Money)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=0)  # average cost of allocated batches
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=0)  # line + promo + allocated invoice discount
    promotion_id: Mapped[int | None] = mapped_column(ForeignKey("promotions.id"))
    tax_rate: Mapped[Decimal] = mapped_column(Rate, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    line_total: Mapped[Decimal] = mapped_column(Money)  # amount the customer pays for this line
    cogs_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    returned_amount: Mapped[Decimal] = mapped_column(Money, default=0)

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(lazy="joined")  # noqa: F821
    allocations: Mapped[list["SaleItemAllocation"]] = relationship(
        back_populates="sale_item", cascade="all, delete-orphan", lazy="selectin", order_by="SaleItemAllocation.id"
    )


class SaleItemAllocation(Base):
    """Which batches supplied a sale line; drives COGS and where returns restock."""

    __tablename__ = "sale_item_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_item_id: Mapped[int] = mapped_column(ForeignKey("sale_items.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_batches.id"))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    returned_quantity: Mapped[Decimal] = mapped_column(Qty, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Money)

    sale_item: Mapped[SaleItem] = relationship(back_populates="allocations")


class SalePayment(Base):
    __tablename__ = "sale_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"), index=True)
    payment_method_id: Mapped[int] = mapped_column(ForeignKey("payment_methods.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    reference_number: Mapped[str | None] = mapped_column(String(80))
    transaction_id: Mapped[str | None] = mapped_column(String(80))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    sale: Mapped[Sale] = relationship(back_populates="payments")
    payment_method: Mapped["PaymentMethod"] = relationship(lazy="joined")  # noqa: F821


class SaleReturn(Base, TimestampMixin):
    __tablename__ = "sale_returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_number: Mapped[str] = mapped_column(String(30), unique=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("cash_register_sessions.id"))
    total_amount: Mapped[Decimal] = mapped_column(Money)  # value of goods returned
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    cogs_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    due_reduced: Mapped[Decimal] = mapped_column(Money, default=0)  # applied against the sale's unpaid balance
    refunded_amount: Mapped[Decimal] = mapped_column(Money, default=0)  # paid back to the customer
    refund_method_id: Mapped[int | None] = mapped_column(ForeignKey("payment_methods.id"))
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    sale: Mapped[Sale] = relationship(lazy="joined")
    items: Mapped[list["SaleReturnItem"]] = relationship(
        back_populates="sale_return", cascade="all, delete-orphan", lazy="selectin"
    )
    refund_method: Mapped["PaymentMethod | None"] = relationship(lazy="joined")  # noqa: F821


class SaleReturnItem(Base):
    __tablename__ = "sale_return_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("sale_returns.id", ondelete="CASCADE"), index=True)
    sale_item_id: Mapped[int] = mapped_column(ForeignKey("sale_items.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    amount: Mapped[Decimal] = mapped_column(Money)
    cogs_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=0)

    sale_return: Mapped[SaleReturn] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(lazy="joined")  # noqa: F821


class Discount(Base, TimestampMixin):
    """Named discount presets a cashier can pick at the POS."""

    __tablename__ = "discounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str | None] = mapped_column(String(30), unique=True)
    discount_type: Mapped[str] = mapped_column(String(10))  # PERCENT | FIXED
    value: Mapped[Decimal] = mapped_column(Money)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Promotion(Base, TimestampMixin):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    promo_type: Mapped[str] = mapped_column(String(20))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("product_categories.id"))
    buy_quantity: Mapped[Decimal] = mapped_column(Qty, default=1)
    get_quantity: Mapped[Decimal] = mapped_column(Qty, default=1)
    value: Mapped[Decimal] = mapped_column(Money, default=0)  # percent or fixed amount
    start_at: Mapped[datetime | None] = mapped_column(DateTime)
    end_at: Mapped[datetime | None] = mapped_column(DateTime)
    days_of_week: Mapped[str | None] = mapped_column(String(20))  # "0,1,2" Monday=0; empty = every day
    start_time: Mapped[str | None] = mapped_column(String(5))  # "17:00" shop-local
    end_time: Mapped[str | None] = mapped_column(String(5))
    priority: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
