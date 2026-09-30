from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select

from app.api.deps import DB, Pagination, has_permission, require
from app.core.errors import NotFoundError, PermissionDenied
from app.models.auth import User
from app.models.base import utcnow
from app.models.customers import Customer
from app.models.enums import CashTxnType
from app.models.finance import CashRegister, CashRegisterSession
from app.models.sales import Discount, DiscountRequest, Promotion, Sale, SalePayment, SaleReturn
from app.repositories.base import apply_sort, like, page_response, paginate
from app.schemas.common import Message, Page
from app.schemas.sales import (
    CartIn,
    CartPreview,
    CashMovementIn,
    CloseSessionIn,
    DiscountDecisionIn,
    DiscountIn,
    DiscountOut,
    DiscountRequestIn,
    DiscountRequestOut,
    OpenSessionIn,
    PreviewLine,
    PromotionIn,
    PromotionOut,
    RegisterIn,
    RegisterOut,
    SaleCreate,
    SaleOut,
    SaleReturnCreate,
    SaleReturnOut,
    SessionOut,
    VoidIn,
)
from app.services import audit, cash_service, discount_service, sales_service, settings_service
from app.utils.dates import get_tz, range_bounds

router = APIRouter(tags=["sales"])


# ---- serialisation --------------------------------------------------------------------

def sale_out(sale: Sale, *, can_cost: bool) -> SaleOut:
    out = SaleOut.model_validate(sale)
    out.customer_name = sale.customer.name if sale.customer else None
    out.customer_phone = sale.customer.phone if sale.customer else None
    out.cashier_name = sale.cashier.full_name
    if not can_cost:
        out.cogs_amount = None
        for i in out.items:
            i.cogs_amount = None
    else:
        for io, i in zip(out.items, sale.items):
            io.cogs_amount = i.cogs_amount
    for po, p in zip(out.payments, sale.payments):
        po.method_name, po.method_type = p.payment_method.name, p.payment_method.method_type
    return out


def _visible(user: User, sale: Sale) -> None:
    if not has_permission(user, "sale.read_all") and sale.cashier_id != user.id:
        raise PermissionDenied("You can only view your own sales")


# ---- POS ------------------------------------------------------------------------------

@router.post("/sales/preview", response_model=CartPreview)
def preview(body: CartIn, db: DB, user: Annotated[User, Depends(require("sale.create"))]):
    """Server-side price/discount/tax calculation for the POS cart (the frontend never computes totals itself)."""
    cart, customer = sales_service.build_cart(db, body)
    allowed, cap = sales_service.check_discount_allowed(db, cart, user)
    lines = [
        PreviewLine(product_id=ln.product.id, name=ln.product.name, quantity=ln.quantity, unit_price=ln.unit_price,
                    gross=ln.gross, auto_discount=ln.auto_discount, promotion=ln.promotion_name,
                    manual_discount=ln.manual_discount, invoice_discount=ln.invoice_discount, discount=ln.total_discount,
                    tax_rate=ln.tax_rate, tax_amount=ln.tax_amount, line_total=ln.line_total,
                    stock_available=ln.product.current_stock)
        for ln in cart.lines
    ]
    return CartPreview(
        lines=lines, subtotal=cart.subtotal, discount_total=cart.discount_total,
        manual_discount_percent=cart.manual_discount_percent, tax_total=cart.tax_total, grand_total=cart.grand_total,
        discount_allowed=allowed, max_discount_percent=cap,
        customer_balance=customer.balance if customer else None,
        credit_available=(max(customer.credit_limit - customer.balance, 0) if customer else None),
    )


@router.post("/sales", response_model=SaleOut, status_code=201)
def create_sale(body: SaleCreate, request: Request, db: DB, user: Annotated[User, Depends(require("sale.create"))]):
    sale = sales_service.create_sale(db, body, user)
    db.commit()
    db.refresh(sale)
    return sale_out(sale, can_cost=has_permission(user, "product.cost"))


@router.get("/sales", response_model=Page[SaleOut])
def list_sales(
    db: DB, p: Pagination, user: Annotated[User, Depends(require("sale.read"))], status: str | None = None,
    customer_id: int | None = None, cashier_id: int | None = None, payment_method_id: int | None = None,
    start: date | None = None, end: date | None = None, has_due: bool | None = None,
):
    stmt = select(Sale).outerjoin(Customer, Customer.id == Sale.customer_id)
    if not has_permission(user, "sale.read_all"):
        stmt = stmt.where(Sale.cashier_id == user.id)
    elif cashier_id:
        stmt = stmt.where(Sale.cashier_id == cashier_id)
    if status:
        stmt = stmt.where(Sale.status == status)
    if customer_id:
        stmt = stmt.where(Sale.customer_id == customer_id)
    if payment_method_id:
        stmt = stmt.where(Sale.payments.any(SalePayment.payment_method_id == payment_method_id))
    if has_due:
        stmt = stmt.where(Sale.due_amount > 0, Sale.status == "COMPLETED")
    if start and end:
        lo, hi = range_bounds(start, end, get_tz(settings_service.get(db, "locale.timezone")))
        stmt = stmt.where(Sale.sale_date >= lo, Sale.sale_date < hi)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(Sale.invoice_number.ilike(t, escape="\\"), Customer.phone.ilike(t, escape="\\"),
                              Customer.name.ilike(t, escape="\\")))
    stmt = apply_sort(stmt, Sale, p.sort, {"sale_date", "total_amount", "invoice_number"}, Sale.id.desc())
    rows, total = paginate(db, stmt, p)
    can_cost = has_permission(user, "product.cost")
    return page_response([sale_out(s, can_cost=can_cost) for s in rows], total, p)


@router.get("/sales/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: int, db: DB, user: Annotated[User, Depends(require("sale.read"))]):
    sale = sales_service.get_sale(db, sale_id)
    _visible(user, sale)
    return sale_out(sale, can_cost=has_permission(user, "product.cost"))


@router.post("/sales/{sale_id}/void", response_model=SaleOut)
def void_sale(sale_id: int, body: VoidIn, db: DB, user: Annotated[User, Depends(require("sale.cancel"))]):
    sale = sales_service.get_sale(db, sale_id, lock=True)
    sales_service.void_sale(db, sale, body.reason, user)
    db.commit()
    return sale_out(sale, can_cost=has_permission(user, "product.cost"))


# ---- returns --------------------------------------------------------------------------

def _return_out(r: SaleReturn) -> SaleReturnOut:
    out = SaleReturnOut.model_validate(r)
    out.invoice_number = r.sale.invoice_number
    out.refund_method_name = r.refund_method.name if r.refund_method else None
    for io, i in zip(out.items, r.items):
        io.product_name = i.product.name
    return out


@router.post("/sale-returns", response_model=SaleReturnOut, status_code=201)
def create_return(body: SaleReturnCreate, db: DB, user: Annotated[User, Depends(require("sale.return"))]):
    sale = sales_service.get_sale(db, body.sale_id)
    _visible(user, sale)
    ret = sales_service.create_return(db, body, user)
    db.commit()
    db.refresh(ret)
    return _return_out(ret)


@router.get("/sale-returns", response_model=Page[SaleReturnOut])
def list_returns(db: DB, p: Pagination, user: Annotated[User, Depends(require("sale.read"))], sale_id: int | None = None,
                 start: date | None = None, end: date | None = None):
    stmt = select(SaleReturn).join(Sale, Sale.id == SaleReturn.sale_id)
    if not has_permission(user, "sale.read_all"):
        stmt = stmt.where(Sale.cashier_id == user.id)
    if sale_id:
        stmt = stmt.where(SaleReturn.sale_id == sale_id)
    if start and end:
        lo, hi = range_bounds(start, end, get_tz(settings_service.get(db, "locale.timezone")))
        stmt = stmt.where(SaleReturn.created_at >= lo, SaleReturn.created_at < hi)
    if p.search:
        t = like(p.search)
        stmt = stmt.where(or_(SaleReturn.return_number.ilike(t, escape="\\"), Sale.invoice_number.ilike(t, escape="\\")))
    rows, total = paginate(db, stmt.order_by(SaleReturn.id.desc()), p)
    return page_response([_return_out(r) for r in rows], total, p)


# ---- cash registers -------------------------------------------------------------------

def _session_out(db: DB, s: CashRegisterSession) -> SessionOut:
    live = cash_service.expected_cash(db, s.id) if s.status == "OPEN" else s.expected_cash
    breakdown = {k: float(v) for k, v in cash_service.breakdown(db, s.id).items()}
    return SessionOut(
        id=s.id, register_id=s.register_id, register_name=s.register.name, opened_by=s.opened_by,
        opened_by_name=s.opener.full_name, opened_at=s.opened_at, closed_at=s.closed_at, opening_cash=s.opening_cash,
        expected_cash=live, actual_cash=s.actual_cash, difference=s.difference,
        discrepancy_reason=s.discrepancy_reason, status=s.status, breakdown=breakdown)


@router.get("/registers", response_model=list[RegisterOut])
def registers(db: DB, _: Annotated[User, Depends(require("register.use", "register.manage", any_of=True))]):
    return list(db.scalars(select(CashRegister).where(CashRegister.is_active.is_(True)).order_by(CashRegister.name)))


@router.post("/registers", response_model=RegisterOut, status_code=201)
def create_register(body: RegisterIn, db: DB, user: Annotated[User, Depends(require("register.manage"))]):
    from app.core.errors import ConflictError

    if db.scalar(select(CashRegister.id).where(CashRegister.name == body.name)):
        raise ConflictError("A register with this name already exists")
    row = CashRegister(**body.model_dump())
    db.add(row)
    db.flush()
    audit.record(db, user=user, action="register.create", entity="register", entity_id=row.id, new=body.model_dump())
    db.commit()
    return row


@router.get("/cash-sessions/current", response_model=SessionOut | None)
def current_session(db: DB, user: Annotated[User, Depends(require("register.use", "register.manage", any_of=True))]):
    s = cash_service.get_open_session(db, user)
    return _session_out(db, s) if s else None


@router.post("/cash-sessions/open", response_model=SessionOut, status_code=201)
def open_session(body: OpenSessionIn, db: DB, user: Annotated[User, Depends(require("register.use"))]):
    s = cash_service.open_session(db, user, body.register_id, body.opening_cash)
    db.commit()
    db.refresh(s)
    return _session_out(db, s)


@router.post("/cash-sessions/{session_id}/close", response_model=SessionOut)
def close_session(session_id: int, body: CloseSessionIn, db: DB, user: Annotated[User, Depends(require("register.use", "register.manage", any_of=True))]):
    s = db.get(CashRegisterSession, session_id)
    if not s:
        raise NotFoundError("Session not found")
    if s.opened_by != user.id and not has_permission(user, "register.manage"):
        raise PermissionDenied("You can only close your own register session")
    cash_service.close_session(db, s, user, body.actual_cash, body.reason)
    db.commit()
    return _session_out(db, s)


@router.post("/cash-sessions/{session_id}/movements", response_model=SessionOut)
def cash_movement(session_id: int, body: CashMovementIn, db: DB, user: Annotated[User, Depends(require("register.use"))]):
    s = db.get(CashRegisterSession, session_id)
    if not s or s.status != "OPEN" or s.opened_by != user.id:
        raise NotFoundError("Open session not found")
    amount = body.amount if body.direction == "IN" else -body.amount
    cash_service.record(db, s.id, CashTxnType.CASH_IN if body.direction == "IN" else CashTxnType.CASH_OUT, amount, user=user, note=body.reason)
    audit.record(db, user=user, action="register.cash_movement", entity="cash_session", entity_id=s.id, new={"direction": body.direction, "amount": body.amount, "reason": body.reason})
    db.commit()
    return _session_out(db, s)


@router.get("/cash-sessions", response_model=Page[SessionOut])
def list_sessions(db: DB, p: Pagination, user: Annotated[User, Depends(require("register.use", "register.manage", any_of=True))],
                  status: str | None = None, start: date | None = None, end: date | None = None):
    stmt = select(CashRegisterSession)
    if not has_permission(user, "register.manage"):
        stmt = stmt.where(CashRegisterSession.opened_by == user.id)
    if status:
        stmt = stmt.where(CashRegisterSession.status == status)
    if start and end:
        lo, hi = range_bounds(start, end, get_tz(settings_service.get(db, "locale.timezone")))
        stmt = stmt.where(CashRegisterSession.opened_at >= lo, CashRegisterSession.opened_at < hi)
    rows, total = paginate(db, stmt.order_by(CashRegisterSession.id.desc()), p)
    return page_response([_session_out(db, s) for s in rows], total, p)


# ---- promotions & discount presets ------------------------------------------------------

@router.get("/promotions", response_model=list[PromotionOut])
def list_promotions(db: DB, _: Annotated[User, Depends(require("sale.create", "promotion.manage", any_of=True))]):
    return list(db.scalars(select(Promotion).order_by(Promotion.id.desc())))


@router.post("/promotions", response_model=PromotionOut, status_code=201)
def create_promotion(body: PromotionIn, db: DB, user: Annotated[User, Depends(require("promotion.manage"))]):
    row = Promotion(**body.model_dump())
    db.add(row)
    db.flush()
    audit.record(db, user=user, action="promotion.create", entity="promotion", entity_id=row.id, new=body.model_dump(mode="json"))
    db.commit()
    return row


@router.put("/promotions/{promo_id}", response_model=PromotionOut)
def update_promotion(promo_id: int, body: PromotionIn, db: DB, user: Annotated[User, Depends(require("promotion.manage"))]):
    row = db.get(Promotion, promo_id)
    if not row:
        raise NotFoundError("Promotion not found")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    audit.record(db, user=user, action="promotion.update", entity="promotion", entity_id=row.id, new=body.model_dump(mode="json"))
    db.commit()
    return row


@router.delete("/promotions/{promo_id}", response_model=Message)
def delete_promotion(promo_id: int, db: DB, user: Annotated[User, Depends(require("promotion.manage"))]):
    row = db.get(Promotion, promo_id)
    if not row:
        raise NotFoundError("Promotion not found")
    row.is_active = False  # historical sale lines reference promotions, so deactivate rather than delete
    audit.record(db, user=user, action="promotion.deactivate", entity="promotion", entity_id=row.id)
    db.commit()
    return Message(message="Promotion deactivated")


@router.get("/discounts", response_model=list[DiscountOut])
def list_discounts(db: DB, _: Annotated[User, Depends(require("sale.create", "promotion.manage", any_of=True))]):
    return list(db.scalars(select(Discount).where(Discount.is_active.is_(True)).order_by(Discount.name)))


@router.post("/discounts", response_model=DiscountOut, status_code=201)
def create_discount(body: DiscountIn, db: DB, user: Annotated[User, Depends(require("promotion.manage"))]):
    row = Discount(**body.model_dump())
    db.add(row)
    db.flush()
    audit.record(db, user=user, action="discount.create", entity="discount", entity_id=row.id, new=body.model_dump(mode="json"))
    db.commit()
    return row


@router.delete("/discounts/{discount_id}", response_model=Message)
def delete_discount(discount_id: int, db: DB, user: Annotated[User, Depends(require("promotion.manage"))]):
    row = db.get(Discount, discount_id)
    if not row:
        raise NotFoundError("Discount not found")
    row.is_active = False
    audit.record(db, user=user, action="discount.deactivate", entity="discount", entity_id=row.id)
    db.commit()
    return Message(message="Discount removed")


# ---- discount approval workflow -------------------------------------------------------

def _request_out(row: DiscountRequest) -> DiscountRequestOut:
    out = DiscountRequestOut.model_validate(row)
    out.status = discount_service.effective_status(row)
    out.requested_by_name = row.requester.full_name
    out.decided_by_name = row.approver.full_name if row.approver else None
    return out


@router.post("/discount-requests", response_model=DiscountRequestOut, status_code=201)
def create_discount_request(body: DiscountRequestIn, db: DB, user: Annotated[User, Depends(require("sale.create"))]):
    row = discount_service.create(db, body, user)
    db.commit()
    db.refresh(row)
    return _request_out(row)


@router.get("/discount-requests", response_model=Page[DiscountRequestOut])
def list_discount_requests(db: DB, p: Pagination, user: Annotated[User, Depends(require("sale.create", "discount.approve", any_of=True))],
                           status: str | None = None):
    stmt = select(DiscountRequest)
    if not has_permission(user, "discount.approve"):
        stmt = stmt.where(DiscountRequest.requested_by == user.id)
    if status == "EXPIRED":
        stmt = stmt.where(DiscountRequest.status.in_(("PENDING", "APPROVED")), DiscountRequest.expires_at < utcnow())
    elif status:
        stmt = stmt.where(DiscountRequest.status == status)
        if status in ("PENDING", "APPROVED"):
            stmt = stmt.where(DiscountRequest.expires_at >= utcnow())
    stmt = stmt.order_by(DiscountRequest.id.desc())
    rows, total = paginate(db, stmt, p)
    return page_response([_request_out(r) for r in rows], total, p)


@router.get("/discount-requests/{request_id}", response_model=DiscountRequestOut)
def get_discount_request(request_id: int, db: DB, user: Annotated[User, Depends(require("sale.create", "discount.approve", any_of=True))]):
    row = discount_service.get(db, request_id)
    if row.requested_by != user.id and not has_permission(user, "discount.approve"):
        raise PermissionDenied("You can only view your own discount requests")
    return _request_out(row)


@router.post("/discount-requests/{request_id}/approve", response_model=DiscountRequestOut)
def approve_discount_request(request_id: int, body: DiscountDecisionIn, db: DB, user: Annotated[User, Depends(require("discount.approve"))]):
    row = discount_service.decide(db, request_id, approve=True, note=body.note, user=user)
    db.commit()
    db.refresh(row)
    return _request_out(row)


@router.post("/discount-requests/{request_id}/reject", response_model=DiscountRequestOut)
def reject_discount_request(request_id: int, body: DiscountDecisionIn, db: DB, user: Annotated[User, Depends(require("discount.approve"))]):
    row = discount_service.decide(db, request_id, approve=False, note=body.note, user=user)
    db.commit()
    db.refresh(row)
    return _request_out(row)
