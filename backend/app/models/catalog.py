from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Money, Qty, Rate, SoftDeleteMixin, TimestampMixin


class ProductCategory(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "product_categories"
    __table_args__ = (UniqueConstraint("name", "parent_id", name="uq_category_name_parent"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    name_bn: Mapped[str | None] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("product_categories.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductBrand(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "product_brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductUnit(Base, TimestampMixin):
    __tablename__ = "product_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    short_name: Mapped[str] = mapped_column(String(15))
    allow_decimal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TaxRate(Base, TimestampMixin):
    """Configurable VAT/tax. Products point at a rate; the rate in force is resolved by effective dates."""

    __tablename__ = "tax_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    rate: Mapped[Decimal] = mapped_column(Rate)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Product(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("purchase_price >= 0", name="ck_product_purchase_price"),
        CheckConstraint("selling_price >= 0", name="ck_product_selling_price"),
        Index("ix_products_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    name_bn: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("product_categories.id"), index=True)
    subcategory_id: Mapped[int | None] = mapped_column(ForeignKey("product_categories.id"))
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("product_brands.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("product_units.id"))
    purchase_price: Mapped[Decimal] = mapped_column(Money, default=0)
    selling_price: Mapped[Decimal] = mapped_column(Money, default=0)
    mrp: Mapped[Decimal | None] = mapped_column(Money)
    tax_rate_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rates.id"))
    discount_percent: Mapped[Decimal] = mapped_column(Rate, default=0)
    min_stock: Mapped[Decimal] = mapped_column(Qty, default=0)
    max_stock: Mapped[Decimal | None] = mapped_column(Qty)
    reorder_level: Mapped[Decimal] = mapped_column(Qty, default=0)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    image_path: Mapped[str | None] = mapped_column(String(255))
    track_expiry: Mapped[bool] = mapped_column(Boolean, default=False)
    track_batch: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    category: Mapped[ProductCategory | None] = relationship(foreign_keys=[category_id], lazy="joined")
    subcategory: Mapped[ProductCategory | None] = relationship(foreign_keys=[subcategory_id], lazy="joined")
    brand: Mapped[ProductBrand | None] = relationship(lazy="joined")
    unit: Mapped[ProductUnit] = relationship(lazy="joined")
    tax_rate: Mapped[TaxRate | None] = relationship(lazy="joined")
    barcodes: Mapped[list["ProductBarcode"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin", order_by="ProductBarcode.id"
    )
    inventory: Mapped["Inventory | None"] = relationship(back_populates="product", uselist=False, lazy="joined")

    @property
    def barcode(self) -> str | None:
        for b in self.barcodes:
            if b.is_primary:
                return b.barcode
        return self.barcodes[0].barcode if self.barcodes else None

    @property
    def current_stock(self) -> Decimal:
        return self.inventory.current_stock if self.inventory else Decimal("0")


class ProductBarcode(Base, TimestampMixin):
    __tablename__ = "product_barcodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    barcode: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    format: Mapped[str] = mapped_column(String(20), default="CODE128")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    product: Mapped[Product] = relationship(back_populates="barcodes")


from app.models.inventory import Inventory  # noqa: E402  (resolve forward reference)
