from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import Num, ORMModel, UTCDateTime


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    name_bn: str | None = Field(default=None, max_length=100)
    parent_id: int | None = None
    is_active: bool = True


class CategoryOut(ORMModel):
    id: int
    name: str
    name_bn: str | None
    parent_id: int | None
    is_active: bool


class BrandIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True


class BrandOut(ORMModel):
    id: int
    name: str
    is_active: bool


class UnitIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    short_name: str = Field(min_length=1, max_length=15)
    allow_decimal: bool = False
    is_active: bool = True


class UnitOut(ORMModel):
    id: int
    name: str
    short_name: str
    allow_decimal: bool
    is_active: bool


class TaxRateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    rate: Decimal = Field(ge=0, le=100)
    effective_from: date | None = None
    effective_to: date | None = None
    is_active: bool = True
    is_default: bool = False

    @model_validator(mode="after")
    def _dates(self):  # noqa: ANN204
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be before effective_from")
        return self


class TaxRateOut(ORMModel):
    id: int
    name: str
    rate: Num
    effective_from: date | None
    effective_to: date | None
    is_active: bool
    is_default: bool


class ProductBase(BaseModel):
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    name_bn: str | None = Field(default=None, max_length=200)
    description: str | None = None
    category_id: int | None = None
    subcategory_id: int | None = None
    brand_id: int | None = None
    unit_id: int
    purchase_price: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("99999999"))
    selling_price: Decimal = Field(ge=0, le=Decimal("99999999"))
    mrp: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999"))
    tax_rate_id: int | None = None
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    min_stock: Decimal = Field(default=Decimal("0"), ge=0)
    max_stock: Decimal | None = Field(default=None, ge=0)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)
    supplier_id: int | None = None
    track_expiry: bool = False
    track_batch: bool = False
    is_active: bool = True

    @field_validator("sku")
    @classmethod
    def _sku(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("SKU is required")
        return v

    @model_validator(mode="after")
    def _stock(self):  # noqa: ANN204
        if self.max_stock is not None and self.max_stock < self.min_stock:
            raise ValueError("max_stock must not be less than min_stock")
        return self


class ProductCreate(ProductBase):
    barcode: str | None = Field(default=None, max_length=64)
    extra_barcodes: list[str] = []
    barcode_format: str = "CODE128"


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=60)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    name_bn: str | None = None
    description: str | None = None
    category_id: int | None = None
    subcategory_id: int | None = None
    brand_id: int | None = None
    unit_id: int | None = None
    purchase_price: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999"))
    selling_price: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999"))
    mrp: Decimal | None = Field(default=None, ge=0)
    tax_rate_id: int | None = None
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    min_stock: Decimal | None = Field(default=None, ge=0)
    max_stock: Decimal | None = Field(default=None, ge=0)
    reorder_level: Decimal | None = Field(default=None, ge=0)
    supplier_id: int | None = None
    track_expiry: bool | None = None
    track_batch: bool | None = None
    is_active: bool | None = None
    barcode: str | None = Field(default=None, max_length=64)


class BarcodeOut(ORMModel):
    id: int
    barcode: str
    format: str
    is_primary: bool


class BarcodeIn(BaseModel):
    barcode: str = Field(min_length=1, max_length=64)
    format: str = "CODE128"
    is_primary: bool = False


class NamedRef(ORMModel):
    id: int
    name: str


class UnitRef(ORMModel):
    id: int
    name: str
    short_name: str
    allow_decimal: bool


class TaxRef(ORMModel):
    id: int
    name: str
    rate: Num


class ProductOut(ORMModel):
    id: int
    sku: str
    barcode: str | None
    barcodes: list[BarcodeOut]
    name: str
    name_bn: str | None
    description: str | None
    category: NamedRef | None
    subcategory: NamedRef | None
    brand: NamedRef | None
    unit: UnitRef
    purchase_price: Num | None  # hidden for users without product.cost
    selling_price: Num
    mrp: Num | None
    tax_rate: TaxRef | None
    discount_percent: Num
    min_stock: Num
    max_stock: Num | None
    reorder_level: Num
    supplier_id: int | None
    image_path: str | None
    track_expiry: bool
    track_batch: bool
    is_active: bool
    current_stock: Num
    created_at: UTCDateTime


class ProductLookup(BaseModel):
    """Lean payload the POS uses for scanning/searching."""

    id: int
    sku: str
    barcode: str | None
    name: str
    name_bn: str | None
    unit: str
    allow_decimal: bool
    selling_price: float
    mrp: float | None
    tax_rate: float
    discount_percent: float
    current_stock: float
    category_id: int | None
    image_path: str | None
    track_expiry: bool
