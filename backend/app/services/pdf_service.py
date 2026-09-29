"""Receipts, invoices and statements as PDF.

Built-in PDF fonts cannot draw the Taka sign or Bangla glyphs, so documents use "Tk" and Latin names.
(The on-screen print views in the web app render the ৳ symbol and Bangla text natively.)
"""

import io
from datetime import UTC
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customers import Customer, CustomerTransaction
from app.models.purchasing import PurchaseOrder, Supplier, SupplierTransaction
from app.models.sales import Sale
from app.services import settings_service
from app.utils.dates import get_tz


def tk(v) -> str:  # noqa: ANN001
    return f"Tk {Decimal(str(v or 0)):,.2f}"


def _shop(db: Session) -> dict:
    return settings_service.get_all(db, public_only=True)


def _local(db: Session, dt) -> str:  # noqa: ANN001

    tz = get_tz(settings_service.get(db, "locale.timezone"))
    return dt.replace(tzinfo=UTC).astimezone(tz).strftime("%d/%m/%Y %I:%M %p")


def receipt_pdf(db: Session, sale: Sale) -> bytes:
    shop = _shop(db)
    width = int(shop.get("receipt.paper_width_mm", 80)) * mm
    lines_needed = 18 + len(sale.items) * 2 + len(sale.payments)
    height = max(lines_needed * 4.2 * mm, 120 * mm)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    y = height - 8 * mm
    margin = 4 * mm

    def center(text: str, size: float = 9, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawCentredString(width / 2, y, text[:48])
        y -= size + 2.5

    def row(left: str, right: str = "", size: float = 8, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(margin, y, left[:34])
        if right:
            c.drawRightString(width - margin, y, right)
        y -= size + 2.2

    def rule() -> None:
        nonlocal y
        c.setDash(1, 2)
        c.line(margin, y + 2, width - margin, y + 2)
        c.setDash()
        y -= 4

    center(str(shop.get("shop.name", "Super Shop")), 12, True)
    center(str(shop.get("shop.address", "")), 7)
    center(f"Tel: {shop.get('shop.phone', '')}", 7)
    if shop.get("shop.bin"):
        center(f"BIN: {shop['shop.bin']}", 7)
    if shop.get("receipt.header"):
        center(str(shop["receipt.header"]), 7)
    rule()
    row(f"Invoice: {sale.invoice_number}", "", 8, True)
    row(f"Date: {_local(db, sale.sale_date)}")
    row(f"Cashier: {sale.cashier.full_name}")
    if sale.customer:
        row(f"Customer: {sale.customer.name}")
    if sale.status == "VOIDED":
        row("*** VOIDED ***", "", 10, True)
    rule()
    for it in sale.items:
        row(it.product_name)
        row(f"  {it.quantity:g} x {Decimal(str(it.unit_price)):,.2f}", tk(it.line_total + it.discount_amount if it.discount_amount else it.line_total).replace("Tk ", ""))
        if it.discount_amount:
            row("  Discount", f"-{Decimal(str(it.discount_amount)):,.2f}", 7)
    rule()
    row("Subtotal", f"{Decimal(str(sale.subtotal)):,.2f}")
    if sale.discount_amount:
        row("Discount", f"-{Decimal(str(sale.discount_amount)):,.2f}")
    if shop.get("receipt.show_tax", True) and sale.tax_amount:
        row("VAT (included)" if shop.get("tax.prices_include_tax", True) else "VAT", f"{Decimal(str(sale.tax_amount)):,.2f}")
    row("TOTAL", tk(sale.total_amount), 10, True)
    rule()
    for p in sale.payments:
        row(p.payment_method.name, f"{Decimal(str(p.amount)):,.2f}")
    if sale.change_amount:
        row("Change", f"{Decimal(str(sale.change_amount)):,.2f}")
    if sale.due_amount:
        row("DUE (credit)", tk(sale.due_amount), 8, True)
    rule()
    center(str(shop.get("receipt.footer", "Thank you!")), 8)
    c.showPage()
    c.save()
    return buf.getvalue()


def _table(data: list[list], col_widths: list[float], header: bool = True, align_right_from: int = 1) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db"))]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def _a4(db: Session, title: str, meta: list[tuple[str, str]], body: list, footer: str = "") -> bytes:
    shop = _shop(db)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title=title)
    st = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=st["Normal"], fontSize=8.5, textColor=colors.HexColor("#4b5563"))
    head = Table([[Paragraph(f"<b>{shop.get('shop.name', 'Super Shop')}</b><br/>{shop.get('shop.address', '')}<br/>Tel {shop.get('shop.phone', '')}"
                             f"{'<br/>BIN ' + str(shop['shop.bin']) if shop.get('shop.bin') else ''}", small),
                   Paragraph(f"<para alignment='right'><font size=16><b>{title}</b></font></para>", st["Normal"])]], colWidths=[100 * mm, 74 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    meta_tbl = Table([[Paragraph(f"<b>{k}</b>", small), Paragraph(v, small)] for k, v in meta], colWidths=[35 * mm, 139 * mm])
    story = [head, Spacer(1, 6 * mm), meta_tbl, Spacer(1, 5 * mm), *body]
    if footer:
        story += [Spacer(1, 8 * mm), Paragraph(footer, small)]
    doc.build(story)
    return buf.getvalue()


def sale_invoice_pdf(db: Session, sale: Sale) -> bytes:
    data = [["#", "Item", "Qty", "Unit price", "Discount", "VAT", "Total"]]
    for i, it in enumerate(sale.items, start=1):
        data.append([i, f"{it.product_name}\n{it.sku}", f"{it.quantity:g}", f"{Decimal(str(it.unit_price)):,.2f}",
                     f"{Decimal(str(it.discount_amount)):,.2f}", f"{Decimal(str(it.tax_amount)):,.2f}", f"{Decimal(str(it.line_total)):,.2f}"])
    items = _table(data, [10 * mm, 66 * mm, 16 * mm, 24 * mm, 20 * mm, 18 * mm, 24 * mm], align_right_from=2)
    totals = [["Subtotal", tk(sale.subtotal)], ["Discount", "-" + tk(sale.discount_amount)], ["VAT", tk(sale.tax_amount)],
              ["Total", tk(sale.total_amount)], ["Paid", tk(sale.paid_amount)]]
    if sale.due_amount:
        totals.append(["Balance due", tk(sale.due_amount)])
    tt = _table(totals, [40 * mm, 34 * mm], header=False)
    tt.hAlign = "RIGHT"
    pays = ", ".join(f"{p.payment_method.name} {tk(p.amount)}" for p in sale.payments) or "-"
    return _a4(db, "INVOICE", [("Invoice no.", sale.invoice_number), ("Date", _local(db, sale.sale_date)),
                               ("Customer", sale.customer.name if sale.customer else "Walk-in customer"), ("Cashier", sale.cashier.full_name),
                               ("Payment", pays), ("Status", sale.status)], [items, Spacer(1, 4 * mm), tt],
               str(_shop(db).get("receipt.footer", "")))


def purchase_invoice_pdf(db: Session, po: PurchaseOrder) -> bytes:
    data = [["#", "Item", "Ordered", "Received", "Unit cost", "Discount", "VAT", "Total"]]
    for i, it in enumerate(po.items, start=1):
        data.append([i, f"{it.product.name}\n{it.product.sku}", f"{it.quantity:g}", f"{it.received_quantity:g}", f"{Decimal(str(it.unit_cost)):,.2f}",
                     f"{Decimal(str(it.discount_amount)):,.2f}", f"{Decimal(str(it.tax_amount)):,.2f}", f"{Decimal(str(it.line_total)):,.2f}"])
    items = _table(data, [8 * mm, 54 * mm, 16 * mm, 16 * mm, 22 * mm, 18 * mm, 16 * mm, 24 * mm], align_right_from=2)
    tt = _table([["Subtotal", tk(po.subtotal)], ["Discount", "-" + tk(po.discount_amount)], ["VAT", tk(po.tax_amount)], ["Total", tk(po.total_amount)],
                 ["Paid", tk(po.paid_amount)]], [40 * mm, 34 * mm], header=False)
    tt.hAlign = "RIGHT"
    return _a4(db, "PURCHASE ORDER", [("PO no.", po.po_number), ("Supplier", po.supplier.name), ("Order date", po.order_date.strftime("%d/%m/%Y")),
                                     ("Status", po.status)], [items, Spacer(1, 4 * mm), tt])


def _statement(db: Session, title: str, party: str, phone: str | None, rows: list, balance) -> bytes:  # noqa: ANN001
    data = [["Date", "Type", "Reference", "Amount", "Balance"]]
    for r in rows:
        data.append([_local(db, r.created_at), r.txn_type, r.reference_number or "", f"{Decimal(str(r.amount)):,.2f}", f"{Decimal(str(r.balance_after)):,.2f}"])
    if len(data) == 1:
        data.append(["No transactions", "", "", "", ""])
    return _a4(db, title, [("Account", party), ("Phone", phone or "-"), ("Current balance", tk(balance))],
               [_table(data, [38 * mm, 26 * mm, 50 * mm, 30 * mm, 30 * mm], align_right_from=3)])


def customer_statement_pdf(db: Session, c: Customer) -> bytes:
    rows = list(db.scalars(select(CustomerTransaction).where(CustomerTransaction.customer_id == c.id).order_by(CustomerTransaction.id).limit(1000)))
    return _statement(db, "CUSTOMER STATEMENT", c.name, c.phone, rows, c.balance)


def supplier_statement_pdf(db: Session, s: Supplier) -> bytes:
    rows = list(db.scalars(select(SupplierTransaction).where(SupplierTransaction.supplier_id == s.id).order_by(SupplierTransaction.id).limit(1000)))
    return _statement(db, "SUPPLIER STATEMENT", s.name, s.phone, rows, s.balance)
