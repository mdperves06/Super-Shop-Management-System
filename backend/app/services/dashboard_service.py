from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.catalog import Product, ProductCategory
from app.models.customers import Customer
from app.models.purchasing import GoodsReceipt, PurchaseOrder, PurchaseReturn, Supplier
from app.models.sales import Sale, SaleItem, SaleReturn
from app.services import financials, inventory_queries, notification_service, settings_service
from app.utils.dates import get_tz, range_bounds, resolve_period

ZERO = Decimal("0")


def pick_granularity(start: date, end: date) -> str:
    days = (end - start).days + 1
    if days <= 1:
        return "hour"
    if days <= 62:
        return "day"
    if days <= 800:
        return "month"
    return "year"


def build(db: Session, user: User, period: str | None, start: date | None, end: date | None,
          top_n: int = 10, granularity: str | None = None) -> dict:
    tz = get_tz(settings_service.get(db, "locale.timezone"))
    d0, d1 = resolve_period(period, start, end, tz)
    lo, hi = range_bounds(d0, d1, tz)
    codes = user.permission_codes
    scope = None if "sale.read_all" in codes else user.id  # cashiers see their own numbers
    finance = "dashboard.finance" in codes
    gran = granularity if granularity in ("hour", "day", "week", "month", "year") else pick_granularity(d0, d1)

    fin = financials.financial_summary(db, lo, hi, tz, cashier_id=scope, with_expenses=finance, with_purchases=finance)
    inv = inventory_queries.summary(db, with_value=finance) if "inventory.read" in codes or finance else None

    kpis: dict = {
        "sales_total": float(fin.sales_total), "invoices": fin.invoices, "returns_total": float(fin.returns_total),
        "discounts": float(fin.discounts),
        "profit": float(fin.gross_profit) if finance else None,
        "net_profit": float(fin.net_profit) if finance else None,
        "expenses": float(fin.expenses) if finance else None,
        "purchases": float(fin.purchases) if finance else None,
        "stock_value": float(inv["stock_value"]) if inv and inv["stock_value"] is not None else None,
        "low_stock": inv["low_stock_count"] if inv else None,
        "out_of_stock": inv["out_of_stock_count"] if inv else None,
        "expiring_soon": inv["expiring_soon_count"] if inv else None,
        "expired": inv["expired_count"] if inv else None,
        "supplier_payables": None, "customer_receivables": None,
    }
    if finance:
        kpis["supplier_payables"] = float(db.scalar(select(func.coalesce(func.sum(Supplier.balance), 0)).where(Supplier.balance > 0, Supplier.is_deleted.is_(False))) or 0)
        kpis["customer_receivables"] = float(db.scalar(select(func.coalesce(func.sum(Customer.balance), 0)).where(Customer.balance > 0, Customer.is_deleted.is_(False))) or 0)

    series = financials.fill_buckets(financials.financial_series(db, lo, hi, tz, gran, cashier_id=scope), d0, d1, gran)
    if not finance:
        for row in series:
            row.pop("cogs"), row.pop("profit"), row.pop("revenue")

    sale_f = [Sale.status == "COMPLETED", Sale.sale_date >= lo, Sale.sale_date < hi]
    if scope:
        sale_f.append(Sale.cashier_id == scope)
    top = db.execute(
        select(SaleItem.product_id, SaleItem.product_name, func.sum(SaleItem.quantity - SaleItem.returned_quantity).label("qty"),
               func.sum(SaleItem.line_total - SaleItem.returned_amount).label("amount"))
        .join(Sale, Sale.id == SaleItem.sale_id).where(*sale_f).group_by(SaleItem.product_id, SaleItem.product_name)
        .order_by(func.sum(SaleItem.quantity - SaleItem.returned_quantity).desc()).limit(min(max(top_n, 1), 50))).all()
    cats = db.execute(
        select(func.coalesce(ProductCategory.name, "Uncategorised"), func.sum(SaleItem.line_total - SaleItem.returned_amount))
        .select_from(SaleItem).join(Sale, Sale.id == SaleItem.sale_id).join(Product, Product.id == SaleItem.product_id)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id).where(*sale_f)
        .group_by(ProductCategory.name).order_by(func.sum(SaleItem.line_total - SaleItem.returned_amount).desc())).all()

    return {
        "period": {"start": d0.isoformat(), "end": d1.isoformat(), "granularity": gran},
        "kpis": kpis,
        "series": series,
        "top_products": [{"product_id": p, "name": n, "quantity": float(q or 0), "amount": float(a or 0)} for p, n, q, a in top],
        "category_sales": [{"category": c, "amount": float(a or 0)} for c, a in cats if (a or 0) != 0],
        "inventory_status": None if not inv else [
            {"status": "Healthy", "count": inv["healthy_count"]}, {"status": "Low stock", "count": inv["low_stock_count"]},
            {"status": "Out of stock", "count": inv["out_of_stock_count"]}, {"status": "Expiring soon", "count": inv["expiring_soon_count"]},
            {"status": "Expired", "count": inv["expired_count"]}],
        "recent": recent_transactions(db, user, scope),
        "unread_notifications": notification_service.unread_count(db, user),
    }


def recent_transactions(db: Session, user: User, scope: int | None, limit: int = 10) -> list[dict]:
    codes = user.permission_codes
    rows: list[tuple[datetime, dict]] = []
    if "sale.read" in codes:
        q = select(Sale).order_by(Sale.id.desc()).limit(limit)
        if scope:
            q = q.where(Sale.cashier_id == scope)
        for s in db.scalars(q).unique():
            rows.append((s.sale_date, {"type": "sale", "id": s.id, "number": s.invoice_number, "party": s.customer.name if s.customer else "Walk-in",
                                       "amount": float(s.total_amount), "status": s.status, "at": s.sale_date.isoformat() + "Z"}))
        q2 = select(SaleReturn).order_by(SaleReturn.id.desc()).limit(5)
        if scope:
            q2 = q2.join(Sale, Sale.id == SaleReturn.sale_id).where(Sale.cashier_id == scope)
        for r in db.scalars(q2).unique():
            rows.append((r.created_at, {"type": "return", "id": r.id, "number": r.return_number, "party": r.sale.invoice_number,
                                        "amount": -float(r.total_amount), "status": "RETURN", "at": r.created_at.isoformat() + "Z"}))
    if "purchase.read" in codes:
        for po in db.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id.desc()).limit(5)).unique():
            rows.append((po.created_at, {"type": "purchase", "id": po.id, "number": po.po_number, "party": po.supplier.name,
                                         "amount": float(po.total_amount), "status": po.status, "at": po.created_at.isoformat() + "Z"}))
    rows.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in rows[:limit]]
