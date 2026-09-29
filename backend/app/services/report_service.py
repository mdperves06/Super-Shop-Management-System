"""Tabular reports. Each report returns the same shape so the API can render JSON, CSV or Excel from it."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.auth import User
from app.models.catalog import Product, ProductCategory
from app.models.customers import Customer
from app.models.finance import CashRegisterSession, Expense, ExpenseCategory, PaymentMethod
from app.models.inventory import Inventory, InventoryTransaction
from app.models.purchasing import GoodsReceipt, PurchaseOrder, PurchaseReturn, Supplier
from app.models.sales import Sale, SaleItem, SalePayment, SaleReturn
from app.services import financials, inventory_queries, settings_service
from app.services.pricing import gross_profit
from app.utils.dates import get_tz, range_bounds, resolve_period
from app.utils.sqlx import local_bucket, utc_offset_minutes

ZERO = Decimal("0")


def col(key: str, label: str, kind: str = "text") -> dict[str, str]:
    return {"key": key, "label": label, "type": kind}  # kind: text | int | money | qty | percent | date


@dataclass
class Report:
    title: str
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]
    summary: dict[str, Any] = field(default_factory=dict)
    period: dict[str, str] | None = None


@dataclass
class Filters:
    lo: datetime
    hi: datetime
    start: date
    end: date
    tz: ZoneInfo
    product_id: int | None = None
    category_id: int | None = None
    supplier_id: int | None = None
    employee_id: int | None = None  # user id of the cashier / employee who made the sale
    payment_method_id: int | None = None
    customer_id: int | None = None
    group_by: str = "day"
    days: int | None = None
    limit: int = 500
    scope_cashier: int | None = None  # restricts to one cashier when the caller may not see everyone


def _f(v) -> float:  # noqa: ANN001
    return float(v or 0)


def _sale_where(f: Filters) -> list:
    w = [Sale.status == "COMPLETED", Sale.sale_date >= f.lo, Sale.sale_date < f.hi]
    if f.employee_id:
        w.append(Sale.cashier_id == f.employee_id)
    if f.scope_cashier:
        w.append(Sale.cashier_id == f.scope_cashier)
    if f.customer_id:
        w.append(Sale.customer_id == f.customer_id)
    if f.payment_method_id:
        w.append(Sale.payments.any(SalePayment.payment_method_id == f.payment_method_id))
    return w


def _item_where(f: Filters) -> list:
    w = _sale_where(f)
    if f.product_id:
        w.append(SaleItem.product_id == f.product_id)
    if f.category_id:
        w.append(or_(Product.category_id == f.category_id, Product.subcategory_id == f.category_id))
    return w


# ---- sales ----------------------------------------------------------------------------

def sales_summary(db: Session, f: Filters, with_profit: bool) -> Report:
    gran = f.group_by if f.group_by in ("day", "week", "month", "year") else "day"
    off = utc_offset_minutes(f.tz)
    bucket = local_bucket(db, Sale.sale_date, off, gran)
    rows = db.execute(select(bucket, func.count(Sale.id), func.sum(Sale.subtotal), func.sum(Sale.discount_amount), func.sum(Sale.tax_amount),
                             func.sum(Sale.total_amount), func.sum(Sale.cogs_amount)).where(*_sale_where(f)).group_by(bucket).order_by(bucket)).all()
    rb = local_bucket(db, SaleReturn.created_at, off, gran)
    rf = [SaleReturn.created_at >= f.lo, SaleReturn.created_at < f.hi, Sale.status == "COMPLETED"]
    if f.employee_id:
        rf.append(Sale.cashier_id == f.employee_id)
    if f.scope_cashier:
        rf.append(Sale.cashier_id == f.scope_cashier)
    rets = {k: (t, tax, c) for k, t, tax, c in db.execute(
        select(rb, func.sum(SaleReturn.total_amount), func.sum(SaleReturn.tax_amount), func.sum(SaleReturn.cogs_amount))
        .join(Sale, Sale.id == SaleReturn.sale_id).where(*rf).group_by(rb))}
    out, tot = [], dict.fromkeys(("n", "gross", "disc", "tax", "net", "ret", "profit"), 0.0)
    seen = set()
    for k, n, gross, disc, tax, total, cogs in rows:
        rt, rtax, rc = (_f(x) for x in rets.get(k, (0, 0, 0)))
        seen.add(k)
        net = _f(total) - rt
        profit = _f(gross_profit(Decimal(str((_f(total) - _f(tax)) - (rt - rtax))), Decimal(str(_f(cogs) - rc))))
        out.append({"period": k, "invoices": n, "gross_sales": _f(gross), "discounts": _f(disc), "tax": _f(tax), "returns": rt,
                    "net_sales": net, "profit": profit})
        for key, val in (("n", n), ("gross", _f(gross)), ("disc", _f(disc)), ("tax", _f(tax)), ("net", net), ("ret", rt), ("profit", profit)):
            tot[key] += val
    columns = [col("period", "Period"), col("invoices", "Invoices", "int"), col("gross_sales", "Gross sales", "money"),
               col("discounts", "Discounts", "money"), col("tax", "VAT", "money"), col("returns", "Returns", "money"),
               col("net_sales", "Net sales", "money")]
    if with_profit:
        columns.append(col("profit", "Gross profit", "money"))
    else:
        for r in out:
            r.pop("profit")
    summary = {"invoices": tot["n"], "gross_sales": tot["gross"], "discounts": tot["disc"], "tax": tot["tax"],
               "returns": tot["ret"], "net_sales": tot["net"]}
    if with_profit:
        summary["profit"] = tot["profit"]
    return Report(f"Sales by {gran}", columns, out, summary)


def sales_by_product(db: Session, f: Filters, with_profit: bool) -> Report:
    q = (select(SaleItem.product_id, SaleItem.product_name, SaleItem.sku, func.sum(SaleItem.quantity - SaleItem.returned_quantity),
                func.sum(SaleItem.line_total - SaleItem.returned_amount), func.sum(SaleItem.tax_amount),
                func.sum(SaleItem.cogs_amount))
         .select_from(SaleItem).join(Sale, Sale.id == SaleItem.sale_id).join(Product, Product.id == SaleItem.product_id)
         .where(*_item_where(f)).group_by(SaleItem.product_id, SaleItem.product_name, SaleItem.sku)
         .order_by(func.sum(SaleItem.line_total - SaleItem.returned_amount).desc()).limit(f.limit))
    rows = []
    for _pid, name, sku, qty, amt, tax, cogs in db.execute(q):
        rows.append({"product": name, "sku": sku, "quantity": _f(qty), "sales": _f(amt), "cogs": _f(cogs),
                     "profit": _f(amt) - _f(tax) - _f(cogs)})
    cols = [col("product", "Product"), col("sku", "SKU"), col("quantity", "Qty sold", "qty"), col("sales", "Sales", "money")]
    if with_profit:
        cols += [col("cogs", "Cost", "money"), col("profit", "Profit (approx.)", "money")]
    else:
        for r in rows:
            r.pop("cogs"), r.pop("profit")
    return Report("Sales by product", cols, rows, {"sales": sum(r["sales"] for r in rows), "quantity": sum(r["quantity"] for r in rows)})


def sales_by_category(db: Session, f: Filters, with_profit: bool) -> Report:
    q = (select(func.coalesce(ProductCategory.name, "Uncategorised"), func.sum(SaleItem.quantity - SaleItem.returned_quantity),
                func.sum(SaleItem.line_total - SaleItem.returned_amount), func.sum(SaleItem.cogs_amount), func.sum(SaleItem.tax_amount))
         .select_from(SaleItem).join(Sale, Sale.id == SaleItem.sale_id).join(Product, Product.id == SaleItem.product_id)
         .outerjoin(ProductCategory, ProductCategory.id == Product.category_id).where(*_item_where(f))
         .group_by(ProductCategory.name).order_by(func.sum(SaleItem.line_total - SaleItem.returned_amount).desc()))
    rows = [{"category": c, "quantity": _f(q_), "sales": _f(a), "cogs": _f(cg), "profit": _f(a) - _f(t) - _f(cg)} for c, q_, a, cg, t in db.execute(q)]
    cols = [col("category", "Category"), col("quantity", "Qty sold", "qty"), col("sales", "Sales", "money")]
    if with_profit:
        cols += [col("cogs", "Cost", "money"), col("profit", "Profit (approx.)", "money")]
    else:
        for r in rows:
            r.pop("cogs"), r.pop("profit")
    return Report("Sales by category", cols, rows, {"sales": sum(r["sales"] for r in rows)})


def sales_by_employee(db: Session, f: Filters, with_profit: bool) -> Report:
    q = (select(Sale.cashier_id, User.full_name, func.count(Sale.id), func.sum(Sale.total_amount), func.sum(Sale.discount_amount),
                func.sum(Sale.returned_amount), func.sum(Sale.cogs_amount), func.sum(Sale.tax_amount))
         .join(User, User.id == Sale.cashier_id).where(*_sale_where(f)).group_by(Sale.cashier_id, User.full_name)
         .order_by(func.sum(Sale.total_amount).desc()))
    rows = [{"employee": n, "invoices": c, "sales": _f(t), "discounts": _f(d), "returns": _f(r),
             "profit": _f(t) - _f(tax) - _f(r) - _f(cg)} for _, n, c, t, d, r, cg, tax in db.execute(q)]
    cols = [col("employee", "Cashier / employee"), col("invoices", "Invoices", "int"), col("sales", "Sales", "money"),
            col("discounts", "Discounts given", "money"), col("returns", "Returns", "money")]
    if with_profit:
        cols.append(col("profit", "Profit (approx.)", "money"))
    else:
        for r in rows:
            r.pop("profit")
    return Report("Sales by cashier", cols, rows, {"sales": sum(r["sales"] for r in rows), "invoices": sum(r["invoices"] for r in rows)})


def sales_by_payment_method(db: Session, f: Filters, _: bool) -> Report:
    q = (select(PaymentMethod.name, func.count(func.distinct(SalePayment.sale_id)), func.sum(SalePayment.amount))
         .select_from(SalePayment).join(Sale, Sale.id == SalePayment.sale_id).join(PaymentMethod, PaymentMethod.id == SalePayment.payment_method_id)
         .where(*_sale_where(f)).group_by(PaymentMethod.name).order_by(func.sum(SalePayment.amount).desc()))
    rows = [{"method": n, "invoices": c, "amount": _f(a)} for n, c, a in db.execute(q)]
    return Report("Sales by payment method", [col("method", "Payment method"), col("invoices", "Invoices", "int"), col("amount", "Amount received", "money")],
                  rows, {"amount": sum(r["amount"] for r in rows)})


def sales_by_customer(db: Session, f: Filters, _: bool) -> Report:
    q = (select(Customer.name, Customer.phone, func.count(Sale.id), func.sum(Sale.total_amount), func.sum(Sale.due_amount))
         .join(Customer, Customer.id == Sale.customer_id).where(*_sale_where(f)).group_by(Customer.id, Customer.name, Customer.phone)
         .order_by(func.sum(Sale.total_amount).desc()).limit(f.limit))
    rows = [{"customer": n, "phone": p or "", "invoices": c, "sales": _f(t), "due": _f(d)} for n, p, c, t, d in db.execute(q)]
    return Report("Sales by customer", [col("customer", "Customer"), col("phone", "Phone"), col("invoices", "Invoices", "int"),
                                        col("sales", "Sales", "money"), col("due", "Unpaid", "money")], rows, {"sales": sum(r["sales"] for r in rows)})


# ---- profit ---------------------------------------------------------------------------

def profit_report(db: Session, f: Filters, _: bool) -> Report:
    gran = f.group_by if f.group_by in ("day", "week", "month", "year") else "day"
    series = financials.financial_series(db, f.lo, f.hi, f.tz, gran)
    rows = [{"period": r["bucket"], "sales": r["sales"], "revenue": r["revenue"], "cogs": r["cogs"], "profit": r["profit"],
             "margin": (r["profit"] / r["revenue"] * 100) if r["revenue"] else 0.0} for r in series]
    fin = financials.financial_summary(db, f.lo, f.hi, f.tz)
    summary = {"sales": float(fin.sales_total), "revenue_ex_vat": float(fin.revenue), "cogs": float(fin.cogs),
               "gross_profit": float(fin.gross_profit), "expenses": float(fin.expenses), "net_profit": float(fin.net_profit),
               "margin_percent": float(fin.gross_profit / fin.revenue * 100) if fin.revenue else 0.0}
    return Report("Profit & loss", [col("period", "Period"), col("sales", "Sales (incl. VAT)", "money"), col("revenue", "Revenue (ex. VAT)", "money"),
                                    col("cogs", "Cost of goods", "money"), col("profit", "Gross profit", "money"), col("margin", "Margin %", "percent")],
                  rows, summary)


def expenses_report(db: Session, f: Filters, _: bool) -> Report:
    q = (select(ExpenseCategory.name, func.count(Expense.id), func.sum(Expense.amount)).join(ExpenseCategory, ExpenseCategory.id == Expense.category_id)
         .where(Expense.status == "ACTIVE", Expense.is_deleted.is_(False), Expense.expense_date >= f.start, Expense.expense_date <= f.end)
         .group_by(ExpenseCategory.name).order_by(func.sum(Expense.amount).desc()))
    rows = [{"category": n, "count": c, "amount": _f(a)} for n, c, a in db.execute(q)]
    return Report("Expenses by category", [col("category", "Category"), col("count", "Entries", "int"), col("amount", "Amount", "money")],
                  rows, {"total": sum(r["amount"] for r in rows)})


def cash_flow(db: Session, f: Filters, _: bool) -> Report:
    fin = financials.financial_summary(db, f.lo, f.hi, f.tz)
    from app.models.finance import Payment

    def paid(direction: str) -> Decimal:
        return Decimal(str(db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.direction == direction, Payment.created_at >= f.lo, Payment.created_at < f.hi)) or 0))

    sales_in = Decimal(str(db.scalar(select(func.coalesce(func.sum(SalePayment.amount), 0)).join(Sale, Sale.id == SalePayment.sale_id).where(
        Sale.status == "COMPLETED", SalePayment.created_at >= f.lo, SalePayment.created_at < f.hi)) or 0))
    refunds = Decimal(str(db.scalar(select(func.coalesce(func.sum(SaleReturn.refunded_amount), 0)).where(
        SaleReturn.created_at >= f.lo, SaleReturn.created_at < f.hi)) or 0))
    customer_in, supplier_out = paid("IN"), paid("OUT")
    rows = [
        {"item": "Cash & card collected at checkout", "inflow": float(sales_in), "outflow": 0.0},
        {"item": "Customer payments received (credit sales)", "inflow": float(customer_in), "outflow": 0.0},
        {"item": "Refunds paid to customers", "inflow": 0.0, "outflow": float(refunds)},
        {"item": "Supplier payments", "inflow": 0.0, "outflow": float(supplier_out)},
        {"item": "Operating expenses", "inflow": 0.0, "outflow": float(fin.expenses)},
    ]
    inflow, outflow = sum(r["inflow"] for r in rows), sum(r["outflow"] for r in rows)
    return Report("Cash flow summary", [col("item", "Item"), col("inflow", "Money in", "money"), col("outflow", "Money out", "money")], rows,
                  {"total_in": inflow, "total_out": outflow, "net_cash_flow": inflow - outflow})


def payables(db: Session, f: Filters, _: bool) -> Report:
    q = select(Supplier).where(Supplier.balance != 0, Supplier.is_deleted.is_(False)).order_by(Supplier.balance.desc())
    rows = [{"supplier": s.name, "phone": s.phone or "", "terms": s.payment_terms_days, "balance": _f(s.balance)} for s in db.scalars(q)]
    return Report("Supplier payables", [col("supplier", "Supplier"), col("phone", "Phone"), col("terms", "Terms (days)", "int"), col("balance", "We owe", "money")],
                  rows, {"total": sum(r["balance"] for r in rows)})


def receivables(db: Session, f: Filters, _: bool) -> Report:
    q = select(Customer).where(Customer.balance != 0, Customer.is_deleted.is_(False)).order_by(Customer.balance.desc())
    rows = [{"customer": c.name, "phone": c.phone or "", "limit": _f(c.credit_limit), "balance": _f(c.balance)} for c in db.scalars(q)]
    return Report("Customer receivables", [col("customer", "Customer"), col("phone", "Phone"), col("limit", "Credit limit", "money"), col("balance", "Owes us", "money")],
                  rows, {"total": sum(r["balance"] for r in rows)})


# ---- inventory ------------------------------------------------------------------------

def inventory_valuation(db: Session, f: Filters, _: bool) -> Report:
    vals = inventory_queries.batch_value_subquery()
    q = (select(Product.sku, Product.name, func.coalesce(ProductCategory.name, "-"), Inventory.current_stock, vals.c.value)
         .join(Inventory, Inventory.product_id == Product.id).join(vals, vals.c.product_id == Product.id)
         .outerjoin(ProductCategory, ProductCategory.id == Product.category_id).where(Product.is_deleted.is_(False)))
    if f.category_id:
        q = q.where(Product.category_id == f.category_id)
    if f.supplier_id:
        q = q.where(Product.supplier_id == f.supplier_id)
    q = q.order_by(vals.c.value.desc()).limit(f.limit)
    rows = []
    for sku, name, cat, stock, value in db.execute(q):
        rows.append({"sku": sku, "product": name, "category": cat, "quantity": _f(stock), "value": _f(value),
                     "avg_cost": _f(value) / _f(stock) if _f(stock) else 0.0})
    return Report("Inventory valuation (FIFO batch cost)", [col("sku", "SKU"), col("product", "Product"), col("category", "Category"),
                                                             col("quantity", "On hand", "qty"), col("avg_cost", "Avg. cost", "money"), col("value", "Stock value", "money")],
                  rows, {"total_value": sum(r["value"] for r in rows), "total_units": sum(r["quantity"] for r in rows)})


def current_inventory(db: Session, f: Filters, with_cost: bool) -> Report:
    q = (select(Product.sku, Product.name, func.coalesce(ProductCategory.name, "-"), Inventory.current_stock, Inventory.damaged_stock,
                Inventory.expired_stock, Product.reorder_level).join(Inventory, Inventory.product_id == Product.id)
         .outerjoin(ProductCategory, ProductCategory.id == Product.category_id).where(Product.is_deleted.is_(False)).order_by(Product.name).limit(f.limit))
    if f.category_id:
        q = q.where(Product.category_id == f.category_id)
    if f.supplier_id:
        q = q.where(Product.supplier_id == f.supplier_id)
    rows = [{"sku": a, "product": b, "category": c, "stock": _f(d), "damaged": _f(e), "expired": _f(g), "reorder": _f(h),
             "status": inventory_queries.stock_status(Decimal(str(d)), Decimal(str(h))).upper()} for a, b, c, d, e, g, h in db.execute(q)]
    return Report("Current inventory", [col("sku", "SKU"), col("product", "Product"), col("category", "Category"), col("stock", "In stock", "qty"),
                                        col("damaged", "Damaged", "qty"), col("expired", "Expired", "qty"), col("reorder", "Reorder level", "qty"), col("status", "Status")],
                  rows, {"products": len(rows)})


def low_stock_report(db: Session, f: Filters, _: bool, *, out_only: bool = False) -> Report:
    cond = [Product.is_deleted.is_(False), Product.is_active.is_(True)]
    cond.append(Inventory.current_stock <= 0 if out_only else Inventory.current_stock <= Product.reorder_level)
    q = (select(Product.sku, Product.name, Inventory.current_stock, Product.reorder_level, Supplier.name)
         .join(Inventory, Inventory.product_id == Product.id).outerjoin(Supplier, Supplier.id == Product.supplier_id).where(*cond)
         .order_by(Inventory.current_stock).limit(f.limit))
    rows = [{"sku": a, "product": b, "stock": _f(c), "reorder": _f(d), "supplier": e or "-", "to_order": max(_f(d) * 2 - _f(c), 0)} for a, b, c, d, e in db.execute(q)]
    return Report("Out of stock" if out_only else "Low stock", [col("sku", "SKU"), col("product", "Product"), col("stock", "In stock", "qty"),
                                                                 col("reorder", "Reorder level", "qty"), col("supplier", "Supplier"), col("to_order", "Suggested order", "qty")],
                  rows, {"products": len(rows)})


def expiry_report(db: Session, f: Filters, with_cost: bool, *, expired: bool = False) -> Report:
    days = f.days or int(settings_service.get(db, "inventory.expiry_warning_days"))
    stmt = inventory_queries.expired_batches_stmt() if expired else inventory_queries.expiring_batches_stmt(days)
    rows = []
    for b in db.scalars(stmt.limit(f.limit)):
        rows.append({"sku": b.product.sku, "product": b.product.name, "batch": b.batch_number, "expiry": b.expiry_date.isoformat(),
                     "days": (b.expiry_date - date.today()).days, "quantity": _f(b.quantity_remaining),
                     "value": _f(b.quantity_remaining * b.purchase_cost) if with_cost else 0.0})
    cols = [col("sku", "SKU"), col("product", "Product"), col("batch", "Batch"), col("expiry", "Expiry date", "date"),
            col("days", "Days left", "int"), col("quantity", "Qty", "qty")]
    if with_cost:
        cols.append(col("value", "Value at cost", "money"))
    else:
        for r in rows:
            r.pop("value")
    return Report("Expired stock" if expired else f"Expiring within {days} days", cols, rows,
                  {"batches": len(rows), "value": sum(r.get("value", 0) for r in rows)})


def stock_movement(db: Session, f: Filters, _: bool) -> Report:
    q = (select(InventoryTransaction, Product.sku).join(Product, Product.id == InventoryTransaction.product_id)
         .where(InventoryTransaction.created_at >= f.lo, InventoryTransaction.created_at < f.hi))
    if f.product_id:
        q = q.where(InventoryTransaction.product_id == f.product_id)
    if f.category_id:
        q = q.where(Product.category_id == f.category_id)
    q = q.order_by(InventoryTransaction.id.desc()).limit(f.limit)
    rows = [{"date": t.created_at.strftime("%Y-%m-%d %H:%M"), "sku": sku, "product": t.product.name, "type": t.txn_type,
             "quantity": _f(t.quantity), "balance": _f(t.balance_after), "reason": t.reason or ""} for t, sku in db.execute(q).unique()]
    return Report("Stock movement", [col("date", "Date (UTC)"), col("sku", "SKU"), col("product", "Product"), col("type", "Type"),
                                     col("quantity", "Qty", "qty"), col("balance", "Balance", "qty"), col("reason", "Reason")], rows, {"movements": len(rows)})


# ---- purchases ------------------------------------------------------------------------

def purchases_by_supplier(db: Session, f: Filters, _: bool) -> Report:
    q = (select(Supplier.name, func.count(func.distinct(GoodsReceipt.purchase_id)), func.sum(GoodsReceipt.value))
         .select_from(GoodsReceipt).join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_id).join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
         .where(GoodsReceipt.received_at >= f.lo, GoodsReceipt.received_at < f.hi).group_by(Supplier.id, Supplier.name).order_by(func.sum(GoodsReceipt.value).desc()))
    if f.supplier_id:
        q = q.where(Supplier.id == f.supplier_id)
    rows = [{"supplier": n, "orders": c, "received": _f(v)} for n, c, v in db.execute(q)]
    return Report("Purchases by supplier", [col("supplier", "Supplier"), col("orders", "Orders", "int"), col("received", "Goods received", "money")],
                  rows, {"total": sum(r["received"] for r in rows)})


def purchases_by_date(db: Session, f: Filters, _: bool) -> Report:
    gran = f.group_by if f.group_by in ("day", "week", "month", "year") else "day"
    b = local_bucket(db, GoodsReceipt.received_at, utc_offset_minutes(f.tz), gran)
    q = select(b, func.count(GoodsReceipt.id), func.sum(GoodsReceipt.value)).where(GoodsReceipt.received_at >= f.lo, GoodsReceipt.received_at < f.hi).group_by(b).order_by(b)
    rows = [{"period": k, "receipts": c, "received": _f(v)} for k, c, v in db.execute(q)]
    return Report(f"Purchases by {gran}", [col("period", "Period"), col("receipts", "Receipts", "int"), col("received", "Goods received", "money")],
                  rows, {"total": sum(r["received"] for r in rows)})


def purchase_returns_report(db: Session, f: Filters, _: bool) -> Report:
    q = (select(PurchaseReturn).where(PurchaseReturn.created_at >= f.lo, PurchaseReturn.created_at < f.hi).order_by(PurchaseReturn.id.desc()).limit(f.limit))
    if f.supplier_id:
        q = q.where(PurchaseReturn.supplier_id == f.supplier_id)
    rows = [{"number": r.return_number, "date": r.return_date.isoformat(), "supplier": r.supplier.name, "amount": _f(r.total_amount), "reason": r.reason}
            for r in db.scalars(q).unique()]
    return Report("Purchase returns", [col("number", "Return #"), col("date", "Date", "date"), col("supplier", "Supplier"), col("amount", "Amount", "money"), col("reason", "Reason")],
                  rows, {"total": sum(r["amount"] for r in rows)})


def register_report(db: Session, f: Filters, _: bool) -> Report:
    q = (select(CashRegisterSession).where(CashRegisterSession.opened_at >= f.lo, CashRegisterSession.opened_at < f.hi).order_by(CashRegisterSession.id.desc()).limit(f.limit))
    rows = [{"session": s.id, "register": s.register.name, "cashier": s.opener.full_name, "opened": s.opened_at.strftime("%Y-%m-%d %H:%M"),
             "opening": _f(s.opening_cash), "expected": _f(s.expected_cash), "actual": _f(s.actual_cash), "difference": _f(s.difference), "status": s.status}
            for s in db.scalars(q).unique()]
    return Report("Cash register sessions", [col("session", "#", "int"), col("register", "Register"), col("cashier", "Cashier"), col("opened", "Opened (UTC)"),
                                             col("opening", "Opening", "money"), col("expected", "Expected", "money"), col("actual", "Counted", "money"),
                                             col("difference", "Difference", "money"), col("status", "Status")], rows,
                  {"discrepancy": sum(r["difference"] for r in rows)})


# ---- registry -------------------------------------------------------------------------

@dataclass
class Spec:
    fn: Callable[..., Report]
    permission: str
    profit_permission: str | None = None  # extra permission that unlocks cost/profit columns
    kwargs: dict = field(default_factory=dict)


REGISTRY: dict[str, Spec] = {
    "sales-summary": Spec(sales_summary, "report.sales", "report.profit"),
    "sales-by-product": Spec(sales_by_product, "report.sales", "report.profit"),
    "sales-by-category": Spec(sales_by_category, "report.sales", "report.profit"),
    "sales-by-employee": Spec(sales_by_employee, "report.sales", "report.profit"),
    "sales-by-payment-method": Spec(sales_by_payment_method, "report.sales"),
    "sales-by-customer": Spec(sales_by_customer, "report.sales"),
    "profit": Spec(profit_report, "report.profit"),
    "expenses": Spec(expenses_report, "report.expenses"),
    "cash-flow": Spec(cash_flow, "report.finance"),
    "payables": Spec(payables, "report.finance"),
    "receivables": Spec(receivables, "report.finance"),
    "cash-registers": Spec(register_report, "report.finance"),
    "inventory-valuation": Spec(inventory_valuation, "report.inventory", "product.cost"),
    "inventory-current": Spec(current_inventory, "report.inventory"),
    "low-stock": Spec(low_stock_report, "report.inventory"),
    "out-of-stock": Spec(low_stock_report, "report.inventory", kwargs={"out_only": True}),
    "expiring": Spec(expiry_report, "report.inventory", "product.cost"),
    "expired": Spec(expiry_report, "report.inventory", "product.cost", kwargs={"expired": True}),
    "stock-movement": Spec(stock_movement, "report.inventory"),
    "purchases-by-supplier": Spec(purchases_by_supplier, "report.purchases"),
    "purchases-by-date": Spec(purchases_by_date, "report.purchases"),
    "purchase-returns": Spec(purchase_returns_report, "report.purchases"),
}


def run(db: Session, name: str, user: User, *, period: str | None, start: date | None, end: date | None, **filters: Any) -> tuple[Report, Spec]:
    spec = REGISTRY.get(name)
    if spec is None:
        raise NotFoundError(f"Unknown report '{name}'")
    codes = user.permission_codes
    tz = get_tz(settings_service.get(db, "locale.timezone"))
    d0, d1 = resolve_period(period or "this_month", start, end, tz)
    lo, hi = range_bounds(d0, d1, tz)
    scope = None if ("sale.read_all" in codes or "report.finance" in codes) else user.id
    f = Filters(lo=lo, hi=hi, start=d0, end=d1, tz=tz, scope_cashier=scope, **{k: v for k, v in filters.items() if v is not None})
    with_extra = True if spec.profit_permission is None else spec.profit_permission in codes
    report = spec.fn(db, f, with_extra, **spec.kwargs)
    report.period = {"start": d0.isoformat(), "end": d1.isoformat()}
    return report, spec
