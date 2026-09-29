"""Central price, discount, promotion and tax arithmetic.

Everything money-related on a sale is computed here on the server. The frontend only *previews*
these numbers by calling the same code path (`POST /sales/preview`).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.models.catalog import Product, TaxRate
from app.models.customers import Customer
from app.models.sales import Promotion
from app.schemas.catalog import ProductLookup
from app.services import settings_service
from app.utils.dates import get_tz

ZERO = Decimal("0")
CENT = Decimal("0.01")

DiscountType = Literal["PERCENT", "FIXED"]


def q2(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def q3(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def effective_tax_rate(rate: TaxRate | None, on: date) -> Decimal:
    """A rate only applies while active and inside its effective window."""
    if rate is None or not rate.is_active:
        return ZERO
    if rate.effective_from and on < rate.effective_from:
        return ZERO
    if rate.effective_to and on > rate.effective_to:
        return ZERO
    return Decimal(rate.rate)


def to_lookup(db: Session, p: Product) -> ProductLookup:
    return ProductLookup(
        id=p.id, sku=p.sku, barcode=p.barcode, name=p.name, name_bn=p.name_bn, unit=p.unit.short_name,
        allow_decimal=p.unit.allow_decimal, selling_price=float(p.selling_price),
        mrp=float(p.mrp) if p.mrp is not None else None,
        tax_rate=float(effective_tax_rate(p.tax_rate, date.today())), discount_percent=float(p.discount_percent),
        current_stock=float(p.current_stock), category_id=p.category_id, image_path=p.image_path,
        track_expiry=p.track_expiry,
    )


# ---- promotions -----------------------------------------------------------------------

def promotion_is_live(promo: Promotion, now_utc: datetime, tz_name: str) -> bool:
    if not promo.is_active:
        return False
    if promo.start_at and now_utc < promo.start_at:
        return False
    if promo.end_at and now_utc > promo.end_at:
        return False
    local = now_utc.replace(tzinfo=timezone.utc).astimezone(get_tz(tz_name))
    if promo.days_of_week:
        days = {int(d) for d in promo.days_of_week.split(",") if d.strip().isdigit()}
        if days and local.weekday() not in days:
            return False
    hhmm = local.strftime("%H:%M")
    if promo.start_time and hhmm < promo.start_time:
        return False
    if promo.end_time and hhmm >= promo.end_time:
        return False
    return True


def promotion_discount(promo: Promotion, product: Product, qty: Decimal, unit_price: Decimal, gross: Decimal,
                       category_ids: set[int]) -> Decimal:
    t = promo.promo_type
    if t == "CATEGORY_PERCENT":
        if promo.category_id not in category_ids:
            return ZERO
        return q2(gross * promo.value / 100)
    if promo.product_id != product.id:
        return ZERO
    if t == "PERCENT_OFF":
        return q2(gross * promo.value / 100)
    if t == "FIXED_OFF":
        return min(gross, q2(promo.value * qty))
    if t == "BUY_X_GET_Y":
        group = promo.buy_quantity + promo.get_quantity
        if group <= 0 or qty < group:
            return ZERO
        sets = (qty // group)
        return q2(sets * promo.get_quantity * unit_price)
    return ZERO


# ---- cart calculation -----------------------------------------------------------------

@dataclass
class LineRequest:
    product: Product
    quantity: Decimal
    discount_type: DiscountType | None = None
    discount_value: Decimal = ZERO


@dataclass
class CalcLine:
    product: Product
    quantity: Decimal
    unit_price: Decimal
    gross: Decimal
    auto_discount: Decimal = ZERO  # product/customer standing discount or promotion
    promotion_id: int | None = None
    promotion_name: str | None = None
    manual_discount: Decimal = ZERO  # cashier-entered line discount
    invoice_discount: Decimal = ZERO  # share of the invoice-level discount
    tax_rate: Decimal = ZERO
    tax_amount: Decimal = ZERO
    line_total: Decimal = ZERO

    @property
    def total_discount(self) -> Decimal:
        return self.auto_discount + self.manual_discount + self.invoice_discount

    @property
    def net_revenue(self) -> Decimal:
        """Revenue excluding tax; the base for profit."""
        return self.line_total - self.tax_amount


@dataclass
class Cart:
    lines: list[CalcLine] = field(default_factory=list)
    subtotal: Decimal = ZERO
    discount_total: Decimal = ZERO
    manual_discount_total: Decimal = ZERO
    tax_total: Decimal = ZERO
    grand_total: Decimal = ZERO

    @property
    def manual_discount_percent(self) -> Decimal:
        if self.subtotal <= 0:
            return ZERO
        return (self.manual_discount_total / self.subtotal * 100).quantize(CENT)


def _manual_amount(kind: DiscountType | None, value: Decimal, base: Decimal) -> Decimal:
    if not kind or value <= 0:
        return ZERO
    if kind == "PERCENT":
        if value > 100:
            raise ValidationFailed("Percentage discount cannot exceed 100%")
        return min(base, q2(base * value / 100))
    return min(base, q2(value))


def calculate_cart(
    db: Session,
    lines: list[LineRequest],
    *,
    invoice_discount_type: DiscountType | None = None,
    invoice_discount_value: Decimal = ZERO,
    customer: Customer | None = None,
    now_utc: datetime | None = None,
) -> Cart:
    if not lines:
        raise ValidationFailed("The cart is empty")
    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    tz_name = settings_service.get(db, "locale.timezone")
    inclusive = settings_service.get_bool(db, "tax.prices_include_tax")
    today = now_utc.replace(tzinfo=timezone.utc).astimezone(get_tz(tz_name)).date()

    promos = [p for p in db.scalars(select(Promotion).where(Promotion.is_active.is_(True)))
              if promotion_is_live(p, now_utc, tz_name)]
    promos.sort(key=lambda p: -p.priority)
    cart = Cart()
    cust_pct = Decimal(customer.discount_percent) if customer else ZERO

    for req in lines:
        p, qty = req.product, req.quantity
        if qty <= 0:
            raise ValidationFailed(f"Quantity for {p.name} must be greater than zero", code="invalid_quantity")
        if not p.unit.allow_decimal and qty != qty.to_integral_value():
            raise ValidationFailed(f"{p.name} is sold in whole {p.unit.name.lower()}s; fractional quantity not allowed")
        unit_price = Decimal(p.selling_price)
        gross = q2(unit_price * qty)
        line = CalcLine(product=p, quantity=qty, unit_price=unit_price, gross=gross,
                        tax_rate=effective_tax_rate(p.tax_rate, today))

        # best automatic discount: standing % (product / customer) vs promotions — they do not stack
        best = q2(gross * max(Decimal(p.discount_percent), cust_pct) / 100)
        cats = {c for c in (p.category_id, p.subcategory_id) if c}
        cats |= {c.parent_id for c in (p.category, p.subcategory) if c is not None and c.parent_id}
        for promo in promos:
            d = promotion_discount(promo, p, qty, unit_price, gross, cats)
            if d > best:
                best, line.promotion_id, line.promotion_name = d, promo.id, promo.name
        line.auto_discount = min(best, gross)
        line.manual_discount = _manual_amount(req.discount_type, req.discount_value, gross - line.auto_discount)
        cart.lines.append(line)

    # invoice-level discount, distributed pro-rata so profit and returns stay exact per line
    base_total = sum((ln.gross - ln.auto_discount - ln.manual_discount for ln in cart.lines), ZERO)
    inv_total = _manual_amount(invoice_discount_type, invoice_discount_value, base_total)
    if inv_total > 0 and base_total > 0:
        remaining = inv_total
        for i, ln in enumerate(cart.lines):
            base = ln.gross - ln.auto_discount - ln.manual_discount
            share = remaining if i == len(cart.lines) - 1 else min(base, q2(inv_total * base / base_total))
            share = min(share, base, remaining)
            ln.invoice_discount = share
            remaining -= share

    for ln in cart.lines:
        net = ln.gross - ln.total_discount
        if inclusive:
            ln.tax_amount = q2(net * ln.tax_rate / (100 + ln.tax_rate)) if ln.tax_rate else ZERO
            ln.line_total = net
        else:
            ln.tax_amount = q2(net * ln.tax_rate / 100)
            ln.line_total = net + ln.tax_amount

    cart.subtotal = sum((ln.gross for ln in cart.lines), ZERO)
    cart.discount_total = sum((ln.total_discount for ln in cart.lines), ZERO)
    cart.manual_discount_total = sum((ln.manual_discount + ln.invoice_discount for ln in cart.lines), ZERO)
    cart.tax_total = sum((ln.tax_amount for ln in cart.lines), ZERO)
    cart.grand_total = sum((ln.line_total for ln in cart.lines), ZERO)
    return cart


def gross_profit(revenue_ex_tax: Decimal, cogs: Decimal) -> Decimal:
    """The one profit formula used everywhere: revenue (net of discounts and tax) minus cost of goods sold."""
    return revenue_ex_tax - cogs
