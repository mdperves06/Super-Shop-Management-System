from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import Num, ORMModel, UTCDateTime
from app.schemas.purchasing import PHONE_RE


class AddressIn(BaseModel):
    label: str = Field(default="Home", max_length=50)
    address: str = Field(min_length=1)
    is_default: bool = False


class AddressOut(ORMModel):
    id: int
    label: str
    address: str
    is_default: bool


class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, pattern=PHONE_RE)
    email: EmailStr | None = None
    address: str | None = None
    customer_type: str = Field(default="RETAIL", pattern="^(RETAIL|WHOLESALE|VIP)$")
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("99999999"))
    is_active: bool = True


class CustomerCreate(CustomerBase):
    opening_balance: Decimal = Field(default=Decimal("0"), ge=0)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    phone: str | None = Field(default=None, pattern=PHONE_RE)
    email: EmailStr | None = None
    address: str | None = None
    customer_type: str | None = Field(default=None, pattern="^(RETAIL|WHOLESALE|VIP)$")
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    credit_limit: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999"))
    is_active: bool | None = None


class CustomerOut(ORMModel):
    id: int
    code: str
    name: str
    phone: str | None
    email: str | None
    address: str | None
    customer_type: str
    loyalty_points: int
    discount_percent: Num
    opening_balance: Num
    balance: Num
    credit_limit: Num
    is_active: bool
    created_at: UTCDateTime
    addresses: list[AddressOut] = []


class CustomerProfile(CustomerOut):
    total_purchases: Num
    total_returns: Num
    total_paid: Num
    sale_count: int
    last_purchase_at: UTCDateTime | None
