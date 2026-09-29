from datetime import date
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import Num, ORMModel, UTCDateTime
from app.schemas.purchasing import PHONE_RE


class ExpenseCategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    is_active: bool = True


class ExpenseCategoryOut(ORMModel):
    id: int
    name: str
    is_active: bool


class ExpenseIn(BaseModel):
    category_id: int
    amount: Decimal = Field(gt=0, le=Decimal("999999999"))
    description: str | None = Field(default=None, max_length=1000)
    expense_date: date | None = None
    payment_method_id: int
    employee_id: int | None = None


class ExpenseUpdate(BaseModel):
    category_id: int | None = None
    amount: Decimal | None = Field(default=None, gt=0, le=Decimal("999999999"))
    description: str | None = None
    expense_date: date | None = None
    employee_id: int | None = None


class ExpenseOut(ORMModel):
    id: int
    expense_number: str
    category_id: int
    category_name: str | None = None
    amount: Num
    description: str | None
    expense_date: date
    payment_method_id: int
    payment_method_name: str | None = None
    employee_id: int | None
    has_attachment: bool = False
    status: str
    void_reason: str | None
    created_at: UTCDateTime
    created_by_name: str | None = None


class VoidExpense(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class EmployeeBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, pattern=PHONE_RE)
    email: EmailStr | None = None
    address: str | None = None
    position: str | None = Field(default=None, max_length=100)
    joining_date: date | None = None
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|INACTIVE|TERMINATED)$")
    user_id: int | None = None
    national_id: str | None = Field(default=None, max_length=50)


class EmployeeCreate(EmployeeBase):
    salary: Decimal = Field(default=Decimal("0"), ge=0)


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    phone: str | None = Field(default=None, pattern=PHONE_RE)
    email: EmailStr | None = None
    address: str | None = None
    position: str | None = None
    joining_date: date | None = None
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE|TERMINATED)$")
    user_id: int | None = None
    national_id: str | None = None
    salary: Decimal | None = Field(default=None, ge=0)


class EmployeeOut(ORMModel):
    id: int
    employee_code: str
    full_name: str
    phone: str | None
    email: str | None
    address: str | None
    position: str | None
    joining_date: date | None
    status: str
    user_id: int | None
    user_email: str | None = None
    salary: Num | None = None  # hidden without employee.salary
    national_id: str | None = None


class AttendanceOut(ORMModel):
    id: int
    employee_id: int
    work_date: date
    check_in: UTCDateTime | None
    check_out: UTCDateTime | None
    status: str
    note: str | None


class EmployeeActivity(BaseModel):
    sales_count: int
    sales_total: Num
    sessions_count: int
    voids_count: int
    recent_actions: list[dict]
