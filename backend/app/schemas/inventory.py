from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AdjustmentType
from app.schemas.common import Num, ORMModel, UTCDateTime


class StockRow(BaseModel):
    product_id: int
    sku: str
    barcode: str | None
    name: str
    category: str | None
    unit: str
    current_stock: Num
    reserved_stock: Num
    available_stock: Num
    damaged_stock: Num
    expired_stock: Num
    reorder_level: Num
    stock_value: Num | None  # hidden without product.cost
    status: str  # out | low | ok


class BatchOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    sku: str
    batch_number: str
    manufacturing_date: date | None
    expiry_date: date | None
    days_to_expiry: int | None
    purchase_cost: Num | None
    quantity_received: Num
    quantity_remaining: Num
    stock_value: Num | None
    received_at: UTCDateTime


class MovementOut(BaseModel):
    id: int
    created_at: UTCDateTime
    product_id: int
    product_name: str
    sku: str
    batch_id: int | None
    batch_number: str | None
    txn_type: str
    quantity: Num
    balance_after: Num
    unit_cost: Num | None
    reference_type: str | None
    reference_id: int | None
    reason: str | None
    user_name: str | None


class AdjustmentCreate(BaseModel):
    product_id: int
    adjustment_type: AdjustmentType
    quantity: Decimal = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    batch_id: int | None = None
    unit_cost: Decimal | None = Field(default=None, ge=0)
    expiry_date: date | None = None
    batch_number: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def _reason(self):  # noqa: ANN204
        if not self.reason.strip():
            raise ValueError("reason is required")
        return self


class AdjustmentOut(ORMModel):
    id: int
    adjustment_number: str
    product_id: int
    batch_id: int | None
    adjustment_type: str
    quantity: Num
    reason: str
    created_at: UTCDateTime
    product_name: str | None = None
    user_name: str | None = None


class InventorySummary(BaseModel):
    stock_value: Num | None
    total_units: Num
    product_count: int
    low_stock_count: int
    out_of_stock_count: int
    expiring_soon_count: int
    expired_count: int
    healthy_count: int
