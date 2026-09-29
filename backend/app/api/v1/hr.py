from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select

from app.api.deps import DB, Pagination, has_permission, require
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models.auth import Attendance, Employee, User
from app.models.base import utcnow
from app.models.enums import CashTxnType
from app.models.finance import CashRegisterSession, Expense, ExpenseCategory, PaymentMethod
from app.models.sales import Sale
from app.models.system import AuditLog
from app.repositories.base import apply_sort, like, page_response, paginate
from app.schemas.common import Message, Page
from app.schemas.hr import (
    AttendanceOut,
    EmployeeActivity,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    ExpenseCategoryIn,
    ExpenseCategoryOut,
    ExpenseIn,
    ExpenseOut,
    ExpenseUpdate,
    VoidExpense,
)
from app.services import audit, cash_service, numbering, settings_service
from app.utils.dates import get_tz, local_today, range_bounds
from app.utils.uploads import DOCUMENT_TYPES, resolve_stored, save_upload

router = APIRouter(tags=["expenses-employees"])


# ---- expenses -------------------------------------------------------------------------

@router.get("/expense-categories", response_model=list[ExpenseCategoryOut])
def expense_categories(db: DB, _: Annotated[User, Depends(require("expense.read", "expense.create", any_of=True))]):
    return list(db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name)))


@router.post("/expense-categories", response_model=ExpenseCategoryOut, status_code=201)
def create_expense_category(body: ExpenseCategoryIn, db: DB, user: Annotated[User, Depends(require("expense.update"))]):
    if db.scalar(select(ExpenseCategory.id).where(func.lower(ExpenseCategory.name) == body.name.lower())):
        raise ConflictError("Category already exists")
    row = ExpenseCategory(**body.model_dump())
    db.add(row)
    db.flush()
    audit.record(db, user=user, action="expense_category.create", entity="expense_category", entity_id=row.id, new=body.model_dump())
    db.commit()
    return row


def _expense_out(e: Expense, names: dict[int, str]) -> ExpenseOut:
    out = ExpenseOut.model_validate(e)
    out.category_name, out.payment_method_name = e.category.name, e.payment_method.name
    out.has_attachment = bool(e.attachment_path)
    out.created_by_name = names.get(e.created_by)
    return out


def _names(db: DB, ids) -> dict[int, str]:  # noqa: ANN001
    ids = {i for i in ids if i}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all()) if ids else {}


@router.get("/expenses", response_model=Page[ExpenseOut])
def list_expenses(db: DB, p: Pagination, _: Annotated[User, Depends(require("expense.read"))], category_id: int | None = None,
                  payment_method_id: int | None = None, employee_id: int | None = None, status: str | None = None,
                  start: date | None = None, end: date | None = None):
    stmt = select(Expense).where(Expense.is_deleted.is_(False))
    if category_id:
        stmt = stmt.where(Expense.category_id == category_id)
    if payment_method_id:
        stmt = stmt.where(Expense.payment_method_id == payment_method_id)
    if employee_id:
        stmt = stmt.where(Expense.employee_id == employee_id)
    if status:
        stmt = stmt.where(Expense.status == status)
    if start:
        stmt = stmt.where(Expense.expense_date >= start)
    if end:
        stmt = stmt.where(Expense.expense_date <= end)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(Expense.description.ilike(t, escape="\\"), Expense.expense_number.ilike(t, escape="\\")))
    stmt = apply_sort(stmt, Expense, p.sort, {"expense_date", "amount", "expense_number"}, Expense.id.desc())
    rows, total = paginate(db, stmt, p)
    names = _names(db, [r.created_by for r in rows])
    return page_response([_expense_out(r, names) for r in rows], total, p)


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(body: ExpenseIn, request: Request, db: DB, user: Annotated[User, Depends(require("expense.create"))]):
    if not db.get(ExpenseCategory, body.category_id):
        raise ValidationFailed("Expense category not found")
    method = db.get(PaymentMethod, body.payment_method_id)
    if not method or not method.is_active:
        raise ValidationFailed("Payment method not found or inactive")
    if body.employee_id and not db.get(Employee, body.employee_id):
        raise ValidationFailed("Employee not found")
    tz = get_tz(settings_service.get(db, "locale.timezone"))
    e = Expense(expense_number=numbering.next_number(db, "EXP"), created_by=user.id,
                expense_date=body.expense_date or local_today(tz), **body.model_dump(exclude={"expense_date"}))
    db.add(e)
    db.flush()
    if method.method_type == "CASH":
        session = cash_service.get_open_session(db, user)
        if session:
            cash_service.record(db, session.id, CashTxnType.EXPENSE, -body.amount, user=user, reference_type="expense",
                                reference_id=e.id, note=f"Expense {e.expense_number}")
    audit.record(db, user=user, action="expense.create", entity="expense", entity_id=e.id,
                 new={"number": e.expense_number, "amount": e.amount, "category_id": e.category_id}, request=request)
    db.commit()
    db.refresh(e)
    return _expense_out(e, {user.id: user.full_name})


def _get_expense(db: DB, expense_id: int) -> Expense:
    e = db.get(Expense, expense_id)
    if not e or e.is_deleted:
        raise NotFoundError("Expense not found")
    return e


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, body: ExpenseUpdate, request: Request, db: DB, user: Annotated[User, Depends(require("expense.update"))]):
    e = _get_expense(db, expense_id)
    if e.status == "VOID":
        raise ConflictError("A voided expense cannot be edited")
    changes = body.model_dump(exclude_unset=True)
    if "amount" in changes and e.payment_method.method_type == "CASH" and changes["amount"] != e.amount:
        raise ValidationFailed("Cash expenses already posted to a register cannot change amount; void and re-enter instead")
    old = {k: getattr(e, k) for k in changes}
    for k, v in changes.items():
        setattr(e, k, v)
    audit.record(db, user=user, action="expense.update", entity="expense", entity_id=e.id, old=old, new=changes, request=request)
    db.commit()
    return _expense_out(e, _names(db, [e.created_by]))


@router.post("/expenses/{expense_id}/void", response_model=ExpenseOut)
def void_expense(expense_id: int, body: VoidExpense, request: Request, db: DB, user: Annotated[User, Depends(require("expense.delete"))]):
    e = _get_expense(db, expense_id)
    if e.status == "VOID":
        raise ConflictError("Expense is already void")
    if e.payment_method.method_type == "CASH":
        session = cash_service.get_open_session(db, user)
        if session:
            cash_service.record(db, session.id, CashTxnType.CASH_IN, e.amount, user=user, reference_type="expense",
                                reference_id=e.id, note=f"Void of {e.expense_number}")
    e.status, e.void_reason = "VOID", body.reason
    audit.record(db, user=user, action="expense.void", entity="expense", entity_id=e.id, new={"reason": body.reason, "amount": e.amount}, request=request)
    db.commit()
    return _expense_out(e, _names(db, [e.created_by]))


@router.post("/expenses/{expense_id}/attachment", response_model=ExpenseOut)
async def upload_attachment(expense_id: int, db: DB, user: Annotated[User, Depends(require("expense.create", "expense.update", any_of=True))],
                            file: UploadFile = File(...)):
    e = _get_expense(db, expense_id)
    path, _, _, _ = await save_upload(file, subdir="attachments", allowed=DOCUMENT_TYPES)
    e.attachment_path = path
    audit.record(db, user=user, action="expense.attachment", entity="expense", entity_id=e.id, new={"file": path})
    db.commit()
    return _expense_out(e, _names(db, [e.created_by]))


@router.get("/expenses/{expense_id}/attachment")
def get_attachment(expense_id: int, db: DB, _: Annotated[User, Depends(require("expense.read"))]):
    e = _get_expense(db, expense_id)
    if not e.attachment_path:
        raise NotFoundError("No attachment")
    path = resolve_stored(e.attachment_path)
    if not path.exists():
        raise NotFoundError("Attachment file is missing")
    return FileResponse(path, headers={"Content-Disposition": f'inline; filename="{path.name}"', "X-Content-Type-Options": "nosniff"})


# ---- employees ------------------------------------------------------------------------

def _employee_out(e: Employee, show_salary: bool, show_id: bool) -> EmployeeOut:
    out = EmployeeOut.model_validate(e)
    out.user_email = e.user.email if e.user else None
    out.salary = e.salary if show_salary else None
    if not show_id:
        out.national_id = None
    return out


@router.get("/employees", response_model=Page[EmployeeOut])
def list_employees(db: DB, p: Pagination, user: Annotated[User, Depends(require("employee.read"))], status: str | None = None):
    stmt = select(Employee).where(Employee.is_deleted.is_(False))
    if status:
        stmt = stmt.where(Employee.status == status)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(Employee.full_name.ilike(t, escape="\\"), Employee.employee_code.ilike(t, escape="\\"),
                              Employee.phone.ilike(t, escape="\\")))
    stmt = apply_sort(stmt, Employee, p.sort, {"full_name", "employee_code", "joining_date"}, Employee.full_name)
    rows, total = paginate(db, stmt, p)
    sal = has_permission(user, "employee.salary")
    return page_response([_employee_out(r, sal, sal) for r in rows], total, p)


def _link_user(db: DB, user_id: int | None, exclude: int | None = None) -> None:
    if user_id is None:
        return
    if not db.get(User, user_id):
        raise ValidationFailed("User account not found")
    q = select(Employee.id).where(Employee.user_id == user_id, Employee.is_deleted.is_(False))
    if exclude:
        q = q.where(Employee.id != exclude)
    if db.scalar(q):
        raise ConflictError("That user account is already linked to another employee")


@router.post("/employees", response_model=EmployeeOut, status_code=201)
def create_employee(body: EmployeeCreate, request: Request, db: DB, user: Annotated[User, Depends(require("employee.create"))]):
    _link_user(db, body.user_id)
    data = body.model_dump()
    if not has_permission(user, "employee.salary"):
        data["salary"] = 0
    e = Employee(employee_code=numbering.next_number(db, "EMP", width=4), **data)
    db.add(e)
    db.flush()
    audit.record(db, user=user, action="employee.create", entity="employee", entity_id=e.id,
                 new={"code": e.employee_code, "name": e.full_name, "position": e.position}, request=request)
    db.commit()
    db.refresh(e)
    return _employee_out(e, has_permission(user, "employee.salary"), has_permission(user, "employee.salary"))


def _get_employee(db: DB, employee_id: int) -> Employee:
    e = db.get(Employee, employee_id)
    if not e or e.is_deleted:
        raise NotFoundError("Employee not found")
    return e


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: int, db: DB, user: Annotated[User, Depends(require("employee.read"))]):
    sal = has_permission(user, "employee.salary")
    return _employee_out(_get_employee(db, employee_id), sal, sal)


@router.patch("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(employee_id: int, body: EmployeeUpdate, request: Request, db: DB, user: Annotated[User, Depends(require("employee.update"))]):
    e = _get_employee(db, employee_id)
    changes = body.model_dump(exclude_unset=True)
    sal = has_permission(user, "employee.salary")
    if "salary" in changes and not sal:
        from app.core.errors import PermissionDenied

        raise PermissionDenied("You do not have permission to change salary information")
    if "user_id" in changes:
        _link_user(db, changes["user_id"], e.id)
    old = {k: getattr(e, k) for k in changes}
    for k, v in changes.items():
        setattr(e, k, v)
    audit.record(db, user=user, action="employee.salary_change" if "salary" in changes else "employee.update",
                 entity="employee", entity_id=e.id, old=old, new=changes, request=request)
    db.commit()
    return _employee_out(e, sal, sal)


@router.delete("/employees/{employee_id}", response_model=Message)
def delete_employee(employee_id: int, request: Request, db: DB, user: Annotated[User, Depends(require("employee.delete"))]):
    e = _get_employee(db, employee_id)
    e.is_deleted, e.status, e.deleted_at, e.user_id = True, "TERMINATED", utcnow(), None
    audit.record(db, user=user, action="employee.delete", entity="employee", entity_id=e.id, request=request)
    db.commit()
    return Message(message="Employee removed")


@router.get("/employees/{employee_id}/activity", response_model=EmployeeActivity)
def employee_activity(employee_id: int, db: DB, _: Annotated[User, Depends(require("employee.read"))]):
    e = _get_employee(db, employee_id)
    if not e.user_id:
        return EmployeeActivity(sales_count=0, sales_total=0, sessions_count=0, voids_count=0, recent_actions=[])
    sales = db.execute(select(func.count(Sale.id), func.coalesce(func.sum(Sale.total_amount), 0))
                       .where(Sale.cashier_id == e.user_id, Sale.status == "COMPLETED")).one()
    sessions = db.scalar(select(func.count(CashRegisterSession.id)).where(CashRegisterSession.opened_by == e.user_id)) or 0
    voids = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.user_id == e.user_id, AuditLog.action == "sale.void")) or 0
    recent = db.scalars(select(AuditLog).where(AuditLog.user_id == e.user_id).order_by(AuditLog.id.desc()).limit(15)).all()
    return EmployeeActivity(
        sales_count=sales[0], sales_total=sales[1], sessions_count=sessions, voids_count=voids,
        recent_actions=[{"at": r.created_at.isoformat() + "Z", "action": r.action, "entity": r.entity, "entity_id": r.entity_id} for r in recent])


@router.get("/employees/{employee_id}/attendance", response_model=list[AttendanceOut])
def attendance(employee_id: int, db: DB, _: Annotated[User, Depends(require("employee.read"))], limit: int = 31):
    e = _get_employee(db, employee_id)
    return list(db.scalars(select(Attendance).where(Attendance.employee_id == e.id).order_by(Attendance.work_date.desc()).limit(min(limit, 366))))


@router.post("/employees/{employee_id}/attendance/check-in", response_model=AttendanceOut, status_code=201)
def check_in(employee_id: int, db: DB, user: Annotated[User, Depends(require("employee.update"))]):
    e = _get_employee(db, employee_id)
    today = local_today(get_tz(settings_service.get(db, "locale.timezone")))
    if db.scalar(select(Attendance.id).where(Attendance.employee_id == e.id, Attendance.work_date == today)):
        raise ConflictError("Already checked in today")
    row = Attendance(employee_id=e.id, work_date=today, check_in=utcnow())
    db.add(row)
    db.commit()
    return row


@router.post("/employees/{employee_id}/attendance/check-out", response_model=AttendanceOut)
def check_out(employee_id: int, db: DB, user: Annotated[User, Depends(require("employee.update"))]):
    e = _get_employee(db, employee_id)
    today = local_today(get_tz(settings_service.get(db, "locale.timezone")))
    row = db.scalar(select(Attendance).where(Attendance.employee_id == e.id, Attendance.work_date == today))
    if not row:
        raise NotFoundError("No check-in found for today")
    if row.check_out:
        raise ConflictError("Already checked out")
    row.check_out = utcnow()
    db.commit()
    return row
