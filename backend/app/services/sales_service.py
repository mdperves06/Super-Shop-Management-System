"""POS sales, voids and returns.

Each public function is a single unit of work: it either completes fully (sale + items + stock +
payments + cash + ledger + audit) or raises, and the caller's rollback leaves nothing behind.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.models.auth import User
from app.models.base import utcnow
from app.models.customers import Customer
from app.models.enums import CashTxnType, InventoryTxnType, LedgerType
from app.models.finance import PaymentMethod
from app.models.sales import (
    Sale,
    SaleItem,
    SaleItemAllocation,
    SalePayment,
    SaleReturn,
    SaleReturnItem,
)
from app.schemas.sales import CartIn, SaleCreate, SaleReturnCreate
from app.services import audit, cash_service, inventory_service, ledger, notification_service, numbering, settings_service
from app.services.pricing import Cart, CalcLine, LineRequest, calculate_cart, q2

ZERO = Decimal("0")


# ---- helpers --------------------------------------------------------------------------

def get_sale(db: Session, sale_id: int, *, lock: bool = False) -> Sale:
    stmt = select(Sale).where(Sale.id == sale_id)
    if lock:
        stmt = stmt.with_for_update()
    sale = db.scalars(stmt).unique().first()
    if not sale:
        raise NotFoundError("Sale not found")
    return sale


def max_discount_percent(db: Session, user: User) -> Decimal:
    if "discount.override" in user.permission_codes:
        return Decimal("100")
    if user.max_discount_percent is not None:
        return Decimal(user.max_discount_percent)
    return settings_service.get_decimal(db, "pos.cashier_max_discount_percent")


def load_customer(db: Session, customer_id: int | None) -> Customer | None:
    if customer_id is None:
        return None
    c = db.get(Customer, customer_id)
    if not c or c.is_deleted or not c.is_active:
        raise ValidationFailed("Customer not found or inactive", code="invalid_customer")
    return c


def build_cart(db: Session, data: CartIn) -> tuple[Cart, Customer | None]:
    from app.services import catalog_service

    customer = load_customer(db, data.customer_id)
    lines = []
    for it in data.items:
        product = catalog_service.get_product(db, it.product_id)
        if not product.is_active:
            raise ValidationFailed(f"{product.name} is inactive and cannot be sold", code="product_inactive")
        lines.append(LineRequest(product, it.quantity, it.discount_type, it.discount_value))
    cart = calculate_cart(db, lines, invoice_discount_type=data.invoice_discount_type,
                          invoice_discount_value=data.invoice_discount_value, customer=customer)
    return cart, customer


def check_discount_allowed(db: Session, cart: Cart, user: User) -> tuple[bool, Decimal]:
    cap = max_discount_percent(db, user)
    return cart.manual_discount_percent <= cap, cap


# ---- create sale ----------------------------------------------------------------------

def create_sale(db: Session, data: SaleCreate, user: User) -> Sale:
    if data.client_ref:
        existing = db.scalar(select(Sale).where(Sale.client_ref == data.client_ref))
        if existing:
            return existing  # retried request: return the sale that was already created
    session = cash_service.get_open_session(db, user)
    if settings_service.get_bool(db, "pos.require_open_register") and session is None:
        raise ConflictError("Open a cash register session before selling", code="register_not_open")

    cart, customer = build_cart(db, data)
    allowed, cap = check_discount_allowed(db, cart, user)
    if not allowed:
        raise PermissionDenied(
            f"Discount of {cart.manual_discount_percent}% exceeds your limit of {cap}%. A manager must approve it.",
            code="discount_limit_exceeded",
            details={"discount_percent": float(cart.manual_discount_percent), "limit": float(cap)})

    total = cart.grand_total
    methods = _load_methods(db, data)
    applied, cash_lines, change, tendered = _settle_payments(data, methods, total)
    paid = sum((a for _, a, _ in applied), ZERO)
    due = total - paid
    if due > 0:
        _authorise_credit(db, user, customer, due)

    sale = Sale(
        invoice_number=numbering.next_number(db, settings_service.get(db, "numbering.invoice_prefix")),
        client_ref=data.client_ref, customer_id=customer.id if customer else None, cashier_id=user.id,
        session_id=session.id if session else None, subtotal=cart.subtotal, discount_amount=cart.discount_total,
        tax_amount=cart.tax_total, total_amount=total, paid_amount=paid, due_amount=due, tendered_amount=tendered,
        change_amount=change, notes=data.notes,
    )
    db.add(sale)
    db.flush()

    cogs_total = ZERO
    for ln in cart.lines:
        item = _add_item(db, sale, ln, user)
        cogs_total += item.cogs_amount
    sale.cogs_amount = cogs_total

    for (line, amount, method) in applied:
        db.add(SalePayment(sale_id=sale.id, payment_method_id=method.id, amount=amount,
                           reference_number=line.reference_number, transaction_id=line.transaction_id, user_id=user.id))
    cash_amount = sum((a for _, a, m in applied if m.method_type == "CASH"), ZERO)
    if cash_amount > 0 and session:
        cash_service.record(db, session.id, CashTxnType.SALE, cash_amount, user=user, reference_type="sale",
                            reference_id=sale.id, note=sale.invoice_number)

    if customer:
        ledger.post_customer(db, customer.id, LedgerType.SALE.value, total, user=user, reference_type="sale",
                             reference_id=sale.id, reference_number=sale.invoice_number, notes="Sale")
        if paid > 0:
            ledger.post_customer(db, customer.id, LedgerType.PAYMENT.value, -paid, user=user, reference_type="sale",
                                 reference_id=sale.id, reference_number=sale.invoice_number, notes="Paid at checkout")
        per100 = int(settings_service.get(db, "pos.loyalty_points_per_100") or 0)
        customer.loyalty_points += int(total // 100) * per100

    audit.record(db, user=user, action="sale.create", entity="sale", entity_id=sale.id,
                 new={"invoice": sale.invoice_number, "total": total, "paid": paid, "due": due,
                      "discount": cart.discount_total, "customer_id": sale.customer_id})
    if cart.manual_discount_total > 0 and cart.manual_discount_percent >= Decimal("10"):
        notification_service.notify(
            db, type="large_discount", severity="warning", title=f"Large discount on {sale.invoice_number}",
            message=f"{user.full_name} gave a {cart.manual_discount_percent}% discount (৳{cart.manual_discount_total:,.2f}) on {sale.invoice_number}.",
            permission="sale.read_all", entity="sale", entity_id=sale.id, dedupe_key=f"disc:{sale.id}")
    db.flush()
    return sale


def _load_methods(db: Session, data: SaleCreate) -> dict[int, PaymentMethod]:
    ids = {p.payment_method_id for p in data.payments}
    methods = {m.id: m for m in db.scalars(select(PaymentMethod).where(PaymentMethod.id.in_(ids)))} if ids else {}
    for p in data.payments:
        m = methods.get(p.payment_method_id)
        if m is None or not m.is_active:
            raise ValidationFailed("Payment method not found or inactive", code="invalid_payment_method")
        if m.requires_reference and not (p.reference_number or p.transaction_id):
            raise ValidationFailed(f"{m.name} requires a reference or transaction ID", code="reference_required")
    return methods


def _settle_payments(data: SaleCreate, methods: dict[int, PaymentMethod], total: Decimal):  # noqa: ANN202
    """Split tendered money into applied payments and change. Only cash can produce change."""
    noncash = sum((q2(p.amount) for p in data.payments if methods[p.payment_method_id].method_type != "CASH"), ZERO)
    cash_tendered = sum((q2(p.amount) for p in data.payments if methods[p.payment_method_id].method_type == "CASH"), ZERO)
    if noncash > total:
        raise ValidationFailed("Card / mobile / bank payments cannot exceed the amount due", code="overpayment")
    cash_needed = max(total - noncash, ZERO)
    cash_applied = min(cash_tendered, cash_needed)
    change = cash_tendered - cash_applied
    applied: list[tuple] = []
    remaining_cash = cash_applied
    for p in data.payments:
        m = methods[p.payment_method_id]
        amt = q2(p.amount)
        if m.method_type == "CASH":
            take = min(amt, remaining_cash)
            remaining_cash -= take
            if take > 0:
                applied.append((p, take, m))
        else:
            applied.append((p, amt, m))
    tendered = noncash + cash_tendered
    return applied, cash_applied, change, tendered


def _authorise_credit(db: Session, user: User, customer: Customer | None, due: Decimal) -> None:
    if customer is None:
        raise ValidationFailed("Payment is less than the total. Select a customer to sell on credit.",
                               code="insufficient_payment", details={"due": float(due)})
    if "sale.credit" not in user.permission_codes:
        raise PermissionDenied("You are not allowed to sell on credit. Collect full payment or ask a manager.",
                               code="credit_not_permitted", details={"due": float(due)})
    available = Decimal(customer.credit_limit) - Decimal(customer.balance)
    if due > available:
        raise ValidationFailed(
            f"Credit limit exceeded: available credit ৳{max(available, ZERO):,.2f}, this sale leaves ৳{due:,.2f} unpaid.",
            code="credit_limit_exceeded", details={"due": float(due), "available": float(max(available, ZERO))})


def _add_item(db: Session, sale: Sale, ln: CalcLine, user: User) -> SaleItem:
    product = ln.product
    item = SaleItem(
        sale_id=sale.id, product_id=product.id, product_name=product.name, sku=product.sku, quantity=ln.quantity,
        unit_price=ln.unit_price, discount_amount=ln.total_discount, promotion_id=ln.promotion_id,
        tax_rate=ln.tax_rate, tax_amount=ln.tax_amount, line_total=ln.line_total,
    )
    sale.items.append(item)
    db.flush()
    allocations = inventory_service.issue_stock(
        db, product, ln.quantity, txn_type=InventoryTxnType.SALE, user=user, reference_type="sale", reference_id=sale.id,
        reason=f"Sale {sale.invoice_number}")
    cogs = ZERO
    for a in allocations:
        item.allocations.append(SaleItemAllocation(batch_id=a.batch_id, quantity=a.quantity, unit_cost=a.unit_cost))
        cogs += a.quantity * a.unit_cost
    item.cogs_amount = q2(cogs)
    item.unit_cost = q2(cogs / ln.quantity) if ln.quantity else ZERO
    return item


# ---- void -----------------------------------------------------------------------------

def void_sale(db: Session, sale: Sale, reason: str, user: User) -> Sale:
    if sale.status != "COMPLETED":
        raise ConflictError("This sale is already voided")
    if sale.return_status != "NONE":
        raise ConflictError("A sale with returns cannot be voided", code="sale_has_returns")
    cash_paid = sum((p.amount for p in sale.payments if p.payment_method.method_type == "CASH"), ZERO)
    session = cash_service.get_open_session(db, user)
    if cash_paid > 0 and session is None:
        raise ConflictError("Open a register session to refund the cash from this sale", code="register_not_open")

    for item in sale.items:
        inventory_service.restock(
            db, item.product, [(a.batch_id, a.quantity - a.returned_quantity, a.unit_cost) for a in item.allocations],
            txn_type=InventoryTxnType.SALE_VOID, user=user, reference_type="sale", reference_id=sale.id,
            reason=f"Void {sale.invoice_number}: {reason}")
    if cash_paid > 0 and session:
        cash_service.record(db, session.id, CashTxnType.SALE_VOID, -cash_paid, user=user, reference_type="sale",
                            reference_id=sale.id, note=f"Void {sale.invoice_number}")
    if sale.customer_id:
        ledger.post_customer(db, sale.customer_id, LedgerType.VOID.value, -sale.total_amount, user=user, reference_type="sale",
                             reference_id=sale.id, reference_number=sale.invoice_number, notes=f"Void: {reason}")
        if sale.paid_amount > 0:
            ledger.post_customer(db, sale.customer_id, LedgerType.VOID.value, sale.paid_amount, user=user, reference_type="sale",
                                 reference_id=sale.id, reference_number=sale.invoice_number, notes="Payment refunded on void")
        per100 = int(settings_service.get(db, "pos.loyalty_points_per_100") or 0)
        cust = db.get(Customer, sale.customer_id)
        if cust:
            cust.loyalty_points = max(cust.loyalty_points - int(sale.total_amount // 100) * per100, 0)
    sale.status, sale.void_reason, sale.voided_by, sale.voided_at = "VOIDED", reason, user.id, utcnow()
    audit.record(db, user=user, action="sale.void", entity="sale", entity_id=sale.id,
                 old={"status": "COMPLETED", "total": sale.total_amount}, new={"status": "VOIDED", "reason": reason},
                 description=f"Voided {sale.invoice_number}")
    return sale


# ---- returns --------------------------------------------------------------------------

def create_return(db: Session, data: SaleReturnCreate, user: User) -> SaleReturn:
    sale = get_sale(db, data.sale_id, lock=True)
    if sale.status != "COMPLETED":
        raise ConflictError("Cannot return items from a voided sale")
    items = {i.id: i for i in sale.items}
    seen: set[int] = set()
    total = tax_total = cogs_total = ZERO
    ret = SaleReturn(return_number=numbering.next_number(db, settings_service.get(db, "numbering.return_prefix")),
                     sale_id=sale.id, customer_id=sale.customer_id, reason=data.reason, created_by=user.id,
                     total_amount=ZERO)
    db.add(ret)
    db.flush()

    for r in data.items:
        item = items.get(r.sale_item_id)
        if item is None:
            raise ValidationFailed("Item does not belong to this sale")
        if r.sale_item_id in seen:
            raise ValidationFailed("Each item may appear only once per return")
        seen.add(r.sale_item_id)
        remaining = item.quantity - item.returned_quantity
        if r.quantity > remaining:
            raise ValidationFailed(f"Only {remaining} of {item.product_name} can still be returned", code="over_return")
        if not item.product.unit.allow_decimal and r.quantity != r.quantity.to_integral_value():
            raise ValidationFailed(f"{item.product_name} can only be returned in whole units")
        completes = r.quantity == remaining
        amount = (item.line_total - item.returned_amount) if completes else q2(item.line_total * r.quantity / item.quantity)
        tax = (item.tax_amount - _returned_tax(db, item)) if completes else q2(item.tax_amount * r.quantity / item.quantity)

        to_restock, cogs, need = [], ZERO, r.quantity
        for alloc in item.allocations:
            avail = alloc.quantity - alloc.returned_quantity
            take = min(avail, need)
            if take <= 0:
                continue
            alloc.returned_quantity += take
            to_restock.append((alloc.batch_id, take, alloc.unit_cost))
            cogs += take * alloc.unit_cost
            need -= take
        inventory_service.restock(db, item.product, to_restock, txn_type=InventoryTxnType.SALE_RETURN, user=user,
                                  reference_type="sale_return", reference_id=ret.id, reason=data.reason)
        item.returned_quantity += r.quantity
        item.returned_amount += amount
        ret.items.append(SaleReturnItem(sale_item_id=item.id, product_id=item.product_id, quantity=r.quantity,
                                        amount=amount, cogs_amount=q2(cogs), tax_amount=tax))
        total += amount
        tax_total += tax
        cogs_total += cogs

    ret.total_amount, ret.tax_amount, ret.cogs_amount = total, tax_total, q2(cogs_total)
    due_reduced = min(total, sale.due_amount) if sale.customer_id else ZERO
    refund = total - due_reduced
    ret.due_reduced, ret.refunded_amount = due_reduced, refund
    sale.due_amount -= due_reduced
    sale.returned_amount += total

    if refund > 0:
        method = db.get(PaymentMethod, data.refund_method_id) if data.refund_method_id else None
        if method is None or not method.is_active:
            raise ValidationFailed("Choose a refund method", code="refund_method_required")
        if method.requires_reference and not data.refund_reference:
            raise ValidationFailed(f"{method.name} refunds need a reference", code="reference_required")
        ret.refund_method_id = method.id
        if method.method_type == "CASH":
            session = cash_service.get_open_session(db, user)
            if session is None:
                raise ConflictError("Open a register session to pay a cash refund", code="register_not_open")
            ret.session_id = session.id
            cash_service.record(db, session.id, CashTxnType.REFUND, -refund, user=user, reference_type="sale_return",
                                reference_id=ret.id, note=f"Refund {ret.return_number}")

    if sale.customer_id:
        ledger.post_customer(db, sale.customer_id, LedgerType.RETURN.value, -total, user=user, reference_type="sale_return",
                             reference_id=ret.id, reference_number=ret.return_number, notes=f"Return against {sale.invoice_number}")
        if refund > 0:
            ledger.post_customer(db, sale.customer_id, LedgerType.PAYMENT.value, refund, user=user, reference_type="sale_return",
                                 reference_id=ret.id, reference_number=ret.return_number, notes="Refund paid to customer")

    fully = all(i.returned_quantity >= i.quantity for i in sale.items)
    sale.return_status = "FULL" if fully else "PARTIAL"
    audit.record(db, user=user, action="sale.return", entity="sale_return", entity_id=ret.id,
                 new={"return": ret.return_number, "invoice": sale.invoice_number, "amount": total, "refund": refund,
                      "reason": data.reason})
    db.flush()
    return ret


def _returned_tax(db: Session, item: SaleItem) -> Decimal:
    """Tax already handed back on earlier partial returns of this line."""
    return Decimal(str(db.scalar(select(func.coalesce(func.sum(SaleReturnItem.tax_amount), 0))
                                 .where(SaleReturnItem.sale_item_id == item.id)) or 0))
