from datetime import date
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.common import Num, ORMModel, UTCDateTime

PHONE_RE = r"^[+0-9][0-9\-\s()]{5,24}$"


class SupplierBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    company: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, pattern=PHONE_RE)
    email: EmailStr | None = None
    address: str | None = None
    contact_person: str | None = Field(default=None, max_length=150)
    tax_id: str | None = Field(default=None, max_length=50)
    payment_terms_days: int = Field(default=0, ge=0, le=365)
    notes: str | None = None
    is_active: bool = True


class SupplierCreate(SupplierBase):
    opening_balance: Decimal = Field(default=Decimal("0"), ge=0)


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    company: str | None = None
    phone: str | None = Field(default=None, pattern=PHONE_RE)
    email: EmailStr | None = None
    address: str | None = None
    contact_person: str | None = None
    tax_id: str | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    notes: str | None = None
    is_active: bool | None = None


class SupplierOut(ORMModel):
    id: int
    code: str
    name: str
    company: str | None
    phone: str | None
    email: str | None
    address: str | None
    contact_person: str | None
    tax_id: str | None
    opening_balance: Num
    balance: Num
    payment_terms_days: int
    notes: str | None
    is_active: bool
    created_at: UTCDateTime


class SupplierProfile(SupplierOut):
    total_purchases: Num
    total_paid: Num
    total_returns: Num
    purchase_count: int


class LedgerRow(BaseModel):
    id: int
    created_at: UTCDateTime
    txn_type: str
    amount: Num
    balance_after: Num
    reference_type: str | None
    reference_id: int | None
    reference_number: str | None
    notes: str | None
    user_name: str | None


class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("999999999"))
    payment_method_id: int
    reference_number: str | None = Field(default=None, max_length=80)
    transaction_id: str | None = Field(default=None, max_length=80)
    purchase_id: int | None = None
    notes: str | None = None


class BalanceAdjustment(BaseModel):
    amount: Decimal  # positive increases the balance, negative decreases it
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("amount")
    @classmethod
    def _nonzero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("Amount must not be zero")
        return v


class PaymentOut(ORMModel):
    id: int
    payment_number: str
    direction: str
    party_type: str
    party_id: int
    amount: Num
    reference_number: str | None
    transaction_id: str | None
    notes: str | None
    method_name: str | None = None
    created_at: UTCDateTime


class PurchaseItemIn(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0, le=Decimal("9999999"))
    unit_cost: Decimal = Field(ge=0, le=Decimal("99999999"))
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class PurchaseCreate(BaseModel):
    supplier_id: int
    order_date: date | None = None
    expected_date: date | None = None
    notes: str | None = None
    items: list[PurchaseItemIn] = Field(min_length=1)
    submit: bool = False

    @model_validator(mode="after")
    def _unique_products(self):  # noqa: ANN204
        ids = [i.product_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product may appear only once per purchase order")
        return self


class PurchaseUpdate(BaseModel):
    supplier_id: int | None = None
    order_date: date | None = None
    expected_date: date | None = None
    notes: str | None = None
    items: list[PurchaseItemIn] | None = Field(default=None, min_length=1)


class PurchaseItemOut(ORMModel):
    id: int
    product_id: int
    product_name: str | None = None
    sku: str | None = None
    track_expiry: bool = False
    quantity: Num
    received_quantity: Num
    returned_quantity: Num
    unit_cost: Num
    discount_amount: Num
    tax_rate: Num
    tax_amount: Num
    line_total: Num
    received_value: Num


class PurchaseOut(ORMModel):
    id: int
    po_number: str
    supplier_id: int
    supplier_name: str | None = None
    status: str
    order_date: date
    expected_date: date | None
    subtotal: Num
    discount_amount: Num
    tax_amount: Num
    total_amount: Num
    received_value: Num
    paid_amount: Num
    notes: str | None
    cancelled_reason: str | None
    created_at: UTCDateTime
    approved_at: UTCDateTime | None
    items: list[PurchaseItemOut]


class ReceiveItem(BaseModel):
    item_id: int
    quantity: Decimal = Field(gt=0)
    batch_number: str | None = Field(default=None, max_length=60)
    manufacturing_date: date | None = None
    expiry_date: date | None = None


class ReceiveIn(BaseModel):
    items: list[ReceiveItem] = Field(min_length=1)
    notes: str | None = None


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PurchaseReturnItemIn(BaseModel):
    product_id: int
    batch_id: int
    quantity: Decimal = Field(gt=0)


class PurchaseReturnCreate(BaseModel):
    supplier_id: int
    purchase_id: int | None = None
    reason: str = Field(min_length=3, max_length=500)
    return_date: date | None = None
    items: list[PurchaseReturnItemIn] = Field(min_length=1)


class PurchaseReturnItemOut(ORMModel):
    id: int
    product_id: int
    product_name: str | None = None
    batch_id: int | None
    quantity: Num
    unit_cost: Num
    amount: Num


class PurchaseReturnOut(ORMModel):
    id: int
    return_number: str
    supplier_id: int
    supplier_name: str | None = None
    purchase_id: int | None
    return_date: date
    total_amount: Num
    reason: str
    created_at: UTCDateTime
    items: list[PurchaseReturnItemOut]


class GoodsReceiptOut(ORMModel):
    id: int
    grn_number: str
    purchase_id: int
    po_number: str | None = None
    supplier_name: str | None = None
    value: Num
    received_at: UTCDateTime
    received_by_name: str | None = None
    notes: str | None
