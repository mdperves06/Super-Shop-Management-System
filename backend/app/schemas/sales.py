from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Num, ORMModel, UTCDateTime


class CartItemIn(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0, le=Decimal("999999"))
    discount_type: Literal["PERCENT", "FIXED"] | None = None
    discount_value: Decimal = Field(default=Decimal("0"), ge=0)


class PaymentLineIn(BaseModel):
    payment_method_id: int
    amount: Decimal = Field(gt=0, le=Decimal("999999999"))
    reference_number: str | None = Field(default=None, max_length=80)
    transaction_id: str | None = Field(default=None, max_length=80)


class CartIn(BaseModel):
    items: list[CartItemIn] = Field(min_length=1, max_length=200)
    customer_id: int | None = None
    invoice_discount_type: Literal["PERCENT", "FIXED"] | None = None
    invoice_discount_value: Decimal = Field(default=Decimal("0"), ge=0)


class SaleCreate(CartIn):
    payments: list[PaymentLineIn] = []
    notes: str | None = Field(default=None, max_length=500)
    client_ref: str | None = Field(default=None, max_length=64)
    discount_request_id: int | None = None  # an APPROVED request lets this sale exceed the cashier's discount limit

    @model_validator(mode="after")
    def _payments(self):  # noqa: ANN204
        return self


class PreviewLine(BaseModel):
    product_id: int
    name: str
    quantity: Num
    unit_price: Num
    gross: Num
    auto_discount: Num
    promotion: str | None
    manual_discount: Num
    invoice_discount: Num
    discount: Num
    tax_rate: Num
    tax_amount: Num
    line_total: Num
    stock_available: Num


class CartPreview(BaseModel):
    lines: list[PreviewLine]
    subtotal: Num
    discount_total: Num
    manual_discount_percent: Num
    tax_total: Num
    grand_total: Num
    discount_allowed: bool
    max_discount_percent: Num
    customer_balance: Num | None = None
    credit_available: Num | None = None


class SaleItemOut(ORMModel):
    id: int
    product_id: int
    product_name: str
    sku: str
    quantity: Num
    returned_quantity: Num
    unit_price: Num
    discount_amount: Num
    tax_rate: Num
    tax_amount: Num
    line_total: Num
    returned_amount: Num
    cogs_amount: Num | None = None


class SalePaymentOut(ORMModel):
    id: int
    payment_method_id: int
    method_name: str | None = None
    method_type: str | None = None
    amount: Num
    reference_number: str | None
    transaction_id: str | None


class SaleOut(ORMModel):
    id: int
    invoice_number: str
    sale_date: UTCDateTime
    status: str
    return_status: str
    customer_id: int | None
    customer_name: str | None = None
    customer_phone: str | None = None
    cashier_id: int
    cashier_name: str | None = None
    subtotal: Num
    discount_amount: Num
    tax_amount: Num
    total_amount: Num
    paid_amount: Num
    due_amount: Num
    tendered_amount: Num
    change_amount: Num
    returned_amount: Num
    cogs_amount: Num | None = None
    notes: str | None
    void_reason: str | None
    items: list[SaleItemOut]
    payments: list[SalePaymentOut]


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ReturnItemIn(BaseModel):
    sale_item_id: int
    quantity: Decimal = Field(gt=0)


class SaleReturnCreate(BaseModel):
    sale_id: int
    items: list[ReturnItemIn] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=500)
    refund_method_id: int | None = None
    refund_reference: str | None = Field(default=None, max_length=80)


class SaleReturnItemOut(ORMModel):
    id: int
    sale_item_id: int
    product_id: int
    product_name: str | None = None
    quantity: Num
    amount: Num


class SaleReturnOut(ORMModel):
    id: int
    return_number: str
    sale_id: int
    invoice_number: str | None = None
    customer_id: int | None
    total_amount: Num
    due_reduced: Num
    refunded_amount: Num
    refund_method_name: str | None = None
    reason: str
    created_at: UTCDateTime
    items: list[SaleReturnItemOut]


# ---- registers -------------------------------------------------------------------------

class RegisterOut(ORMModel):
    id: int
    name: str
    location: str | None
    is_active: bool


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    location: str | None = None
    is_active: bool = True


class OpenSessionIn(BaseModel):
    register_id: int
    opening_cash: Decimal = Field(ge=0, le=Decimal("99999999"))


class CloseSessionIn(BaseModel):
    actual_cash: Decimal = Field(ge=0, le=Decimal("999999999"))
    reason: str | None = Field(default=None, max_length=500)


class CashMovementIn(BaseModel):
    direction: Literal["IN", "OUT"]
    amount: Decimal = Field(gt=0, le=Decimal("99999999"))
    reason: str = Field(min_length=3, max_length=255)


class SessionOut(BaseModel):
    id: int
    register_id: int
    register_name: str
    opened_by: int
    opened_by_name: str
    opened_at: UTCDateTime
    closed_at: UTCDateTime | None
    opening_cash: Num
    expected_cash: Num  # live value while open
    actual_cash: Num | None
    difference: Num | None
    discrepancy_reason: str | None
    status: str
    breakdown: dict[str, float] = {}


# ---- promotions / discounts -------------------------------------------------------------

class PromotionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    promo_type: Literal["BUY_X_GET_Y", "PERCENT_OFF", "FIXED_OFF", "CATEGORY_PERCENT"]
    product_id: int | None = None
    category_id: int | None = None
    buy_quantity: Decimal = Field(default=Decimal("1"), gt=0)
    get_quantity: Decimal = Field(default=Decimal("1"), ge=0)
    value: Decimal = Field(default=Decimal("0"), ge=0)
    start_at: UTCDateTime | None = None
    end_at: UTCDateTime | None = None
    days_of_week: str | None = Field(default=None, pattern=r"^[0-6](,[0-6])*$")
    start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    priority: int = 0
    is_active: bool = True

    @model_validator(mode="after")
    def _shape(self):  # noqa: ANN204
        t = self.promo_type
        if t == "CATEGORY_PERCENT":
            if not self.category_id:
                raise ValueError("category_id is required for category promotions")
        elif not self.product_id:
            raise ValueError("product_id is required for this promotion type")
        if t in ("PERCENT_OFF", "CATEGORY_PERCENT") and self.value > 100:
            raise ValueError("Percentage cannot exceed 100")
        if t == "BUY_X_GET_Y" and self.get_quantity <= 0:
            raise ValueError("get_quantity must be positive")
        if t in ("PERCENT_OFF", "CATEGORY_PERCENT", "FIXED_OFF") and self.value <= 0:
            raise ValueError("value must be positive")
        return self


class PromotionOut(ORMModel):
    id: int
    name: str
    promo_type: str
    product_id: int | None
    category_id: int | None
    buy_quantity: Num
    get_quantity: Num
    value: Num
    start_at: UTCDateTime | None
    end_at: UTCDateTime | None
    days_of_week: str | None
    start_time: str | None
    end_time: str | None
    priority: int
    is_active: bool


class DiscountIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str | None = Field(default=None, max_length=30)
    discount_type: Literal["PERCENT", "FIXED"]
    value: Decimal = Field(gt=0)
    requires_approval: bool = False
    is_active: bool = True

    @model_validator(mode="after")
    def _pct(self):  # noqa: ANN204
        if self.discount_type == "PERCENT" and self.value > 100:
            raise ValueError("Percentage cannot exceed 100")
        return self


class DiscountOut(ORMModel):
    id: int
    name: str
    code: str | None
    discount_type: str
    value: Num
    requires_approval: bool
    is_active: bool


# ---- discount approval ----------------------------------------------------------------

class DiscountRequestIn(CartIn):
    reason: str = Field(min_length=3, max_length=500)


class DiscountDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class DiscountRequestOut(ORMModel):
    id: int
    status: str
    discount_percent: Num
    discount_amount: Num
    reason: str
    cart_snapshot: dict
    requested_by: int
    requested_by_name: str | None = None
    decided_by: int | None
    decided_by_name: str | None = None
    decided_at: UTCDateTime | None
    decision_note: str | None
    expires_at: UTCDateTime
    used_sale_id: int | None
    created_at: UTCDateTime
