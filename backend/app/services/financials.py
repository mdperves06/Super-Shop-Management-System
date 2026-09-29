"""The one place revenue, COGS, profit and expenses are aggregated.

Definitions (also documented in docs/FINANCE.md):
  revenue       = sum(line_total - tax) of completed sales        (discounts already deducted, VAT excluded)
  net revenue   = revenue - (return value - return tax)           (returns count on the day they happen)
  COGS          = cost of the batches actually sold, minus cost of goods returned
  gross profit  = net revenue - COGS                              (pricing.gross_profit)
  net profit    = gross profit - active expenses
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import Expense
from app.models.purchasing import GoodsReceipt, PurchaseReturn
from app.models.sales import Sale, SaleReturn
from app.services.pricing import gross_profit
from app.utils.sqlx import local_bucket, utc_offset_minutes

ZERO = Decimal("0")


def _d(v) -> Decimal:  # noqa: ANN001
    return Decimal(str(v or 0))


@dataclass
class Financials:
    invoices: int = 0
    gross_sales: Decimal = ZERO      # before discounts, incl. nothing else
    discounts: Decimal = ZERO
    tax_collected: Decimal = ZERO
    sales_total: Decimal = ZERO      # customer-facing total incl. VAT, minus returns
    revenue: Decimal = ZERO          # net of discounts and VAT, minus returns
    cogs: Decimal = ZERO
    gross_profit: Decimal = ZERO
    expenses: Decimal = ZERO
    net_profit: Decimal = ZERO
    returns_total: Decimal = ZERO
    purchases: Decimal = ZERO
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items() if k != "extra"}


def financial_summary(db: Session, lo: datetime, hi: datetime, tz: ZoneInfo, *, cashier_id: int | None = None,
                      with_expenses: bool = True, with_purchases: bool = True) -> Financials:
    sale_filter = [Sale.status == "COMPLETED", Sale.sale_date >= lo, Sale.sale_date < hi]
    ret_filter = [SaleReturn.created_at >= lo, SaleReturn.created_at < hi, Sale.status == "COMPLETED"]
    if cashier_id:
        sale_filter.append(Sale.cashier_id == cashier_id)
        ret_filter.append(Sale.cashier_id == cashier_id)

    s = db.execute(select(func.count(Sale.id), func.coalesce(func.sum(Sale.subtotal), 0), func.coalesce(func.sum(Sale.discount_amount), 0),
                          func.coalesce(func.sum(Sale.tax_amount), 0), func.coalesce(func.sum(Sale.total_amount), 0),
                          func.coalesce(func.sum(Sale.cogs_amount), 0)).where(*sale_filter)).one()
    r = db.execute(select(func.coalesce(func.sum(SaleReturn.total_amount), 0), func.coalesce(func.sum(SaleReturn.tax_amount), 0),
                          func.coalesce(func.sum(SaleReturn.cogs_amount), 0))
                   .join(Sale, Sale.id == SaleReturn.sale_id).where(*ret_filter)).one()
    fin = Financials()
    fin.invoices = s[0]
    fin.gross_sales, fin.discounts, fin.tax_collected = _d(s[1]), _d(s[2]), _d(s[3])
    fin.returns_total = _d(r[0])
    fin.sales_total = _d(s[4]) - fin.returns_total
    fin.revenue = (_d(s[4]) - _d(s[3])) - (_d(r[0]) - _d(r[1]))
    fin.cogs = _d(s[5]) - _d(r[2])
    fin.gross_profit = gross_profit(fin.revenue, fin.cogs)

    if with_expenses:
        start_local, end_local = _local_dates(lo, hi, tz)
        fin.expenses = _d(db.scalar(select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.status == "ACTIVE", Expense.is_deleted.is_(False), Expense.expense_date >= start_local, Expense.expense_date <= end_local)))
    fin.net_profit = fin.gross_profit - fin.expenses
    if with_purchases:
        received = _d(db.scalar(select(func.coalesce(func.sum(GoodsReceipt.value), 0)).where(GoodsReceipt.received_at >= lo, GoodsReceipt.received_at < hi)))
        returned = _d(db.scalar(select(func.coalesce(func.sum(PurchaseReturn.total_amount), 0)).where(PurchaseReturn.created_at >= lo, PurchaseReturn.created_at < hi)))
        fin.purchases = received - returned
        fin.extra["purchase_returns"] = returned
    return fin


def _local_dates(lo: datetime, hi: datetime, tz: ZoneInfo) -> tuple[date, date]:
    from datetime import timedelta

    a = lo.replace(tzinfo=UTC).astimezone(tz).date()
    b = (hi - timedelta(seconds=1)).replace(tzinfo=UTC).astimezone(tz).date()
    return a, b


def financial_series(db: Session, lo: datetime, hi: datetime, tz: ZoneInfo, granularity: str, *,
                     cashier_id: int | None = None) -> list[dict]:
    """Sales / revenue / cost / profit per bucket, computed with the same definitions as financial_summary."""
    off = utc_offset_minutes(tz)
    b_sale = local_bucket(db, Sale.sale_date, off, granularity)
    f = [Sale.status == "COMPLETED", Sale.sale_date >= lo, Sale.sale_date < hi]
    if cashier_id:
        f.append(Sale.cashier_id == cashier_id)
    sales = {k: (_d(t), _d(tax), _d(c), n) for k, t, tax, c, n in db.execute(
        select(b_sale, func.sum(Sale.total_amount), func.sum(Sale.tax_amount), func.sum(Sale.cogs_amount), func.count(Sale.id)).where(*f).group_by(b_sale))}
    b_ret = local_bucket(db, SaleReturn.created_at, off, granularity)
    rf = [SaleReturn.created_at >= lo, SaleReturn.created_at < hi, Sale.status == "COMPLETED"]
    if cashier_id:
        rf.append(Sale.cashier_id == cashier_id)
    rets = {k: (_d(t), _d(tax), _d(c)) for k, t, tax, c in db.execute(
        select(b_ret, func.sum(SaleReturn.total_amount), func.sum(SaleReturn.tax_amount), func.sum(SaleReturn.cogs_amount))
        .join(Sale, Sale.id == SaleReturn.sale_id).where(*rf).group_by(b_ret))}
    out = []
    for key in sorted(set(sales) | set(rets)):
        t, tax, c, n = sales.get(key, (ZERO, ZERO, ZERO, 0))
        rt, rtax, rc = rets.get(key, (ZERO, ZERO, ZERO))
        revenue = (t - tax) - (rt - rtax)
        cogs = c - rc
        out.append({"bucket": key, "sales": float(t - rt), "revenue": float(revenue), "cogs": float(cogs),
                    "profit": float(gross_profit(revenue, cogs)), "invoices": n})
    return out


def fill_buckets(series: list[dict], start: date, end: date, granularity: str) -> list[dict]:
    """Insert zero rows so charts show empty days instead of skipping them."""
    if granularity != "day":
        return series
    from datetime import timedelta

    have = {row["bucket"]: row for row in series}
    out, d = [], start
    while d <= end and (end - start).days <= 400:
        key = d.isoformat()
        out.append(have.get(key, {"bucket": key, "sales": 0.0, "revenue": 0.0, "cogs": 0.0, "profit": 0.0, "invoices": 0}))
        d += timedelta(days=1)
    return out
