"""Receipts, invoices and statements as PDF.

Built with fpdf2 + HarfBuzz text shaping and a bundled Noto Sans Bengali (SIL OFL, app/assets/fonts), so Bangla
conjuncts, vowel signs and the ৳ sign render correctly on any OS, including slim Linux containers with no system fonts.
"""

from datetime import UTC
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import Align
from fpdf.fonts import FontFace
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customers import Customer, CustomerTransaction
from app.models.purchasing import PurchaseOrder, Supplier, SupplierTransaction
from app.models.sales import Sale
from app.services import settings_service
from app.utils.dates import get_tz

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FAMILY = "NotoBn"


def _grouped(n: Decimal) -> str:
    """South-Asian digit grouping (12,34,567.50), matching the web app."""
    sign = "-" if n < 0 else ""
    whole, _, frac = f"{abs(n):.2f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    if head:
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        tail = ",".join(parts) + "," + tail
    return f"{sign}{tail}.{frac}"


def num(v) -> str:  # noqa: ANN001
    return _grouped(Decimal(str(v or 0)))


def tk(v) -> str:  # noqa: ANN001
    n = Decimal(str(v or 0))
    return f"-৳{_grouped(-n)}" if n < 0 else f"৳{_grouped(n)}"


def qty(v) -> str:  # noqa: ANN001
    return f"{Decimal(str(v or 0)):f}".rstrip("0").rstrip(".") or "0"


def _new_pdf(format: str | tuple[float, float] = "A4", orientation: str = "P", margin: float = 12) -> FPDF:  # noqa: A002
    pdf = FPDF(orientation=orientation, unit="mm", format=format)
    pdf.add_font(FAMILY, "", str(FONT_DIR / "NotoSansBengali-Regular.ttf"))
    pdf.add_font(FAMILY, "B", str(FONT_DIR / "NotoSansBengali-Bold.ttf"))
    pdf.set_text_shaping(True)  # HarfBuzz: required for correct Bengali glyph shaping
    pdf.set_margins(margin, margin, margin)
    pdf.set_auto_page_break(True, margin)
    pdf.set_creator("Super Shop Management")
    pdf.set_font(FAMILY, "", 9)
    return pdf


def _shop(db: Session) -> dict:
    return settings_service.get_all(db, public_only=True)


def _local(db: Session, dt) -> str:  # noqa: ANN001
    tz = get_tz(settings_service.get(db, "locale.timezone"))
    return dt.replace(tzinfo=UTC).astimezone(tz).strftime("%d/%m/%Y %I:%M %p")


def _output(pdf: FPDF) -> bytes:
    return bytes(pdf.output())


def _names(product) -> tuple[str, str | None]:  # noqa: ANN001
    return product.name, product.name_bn


# ---------------------------------------------------------------- thermal receipt

def receipt_pdf(db: Session, sale: Sale) -> bytes:
    shop = _shop(db)
    width = float(shop.get("receipt.paper_width_mm", 80))

    def draw(pdf: FPDF) -> float:
        m = 3.5
        w = width - 2 * m

        def line(text: str, size: float = 8, bold: bool = False, align: str = "L") -> None:
            pdf.set_font(FAMILY, "B" if bold else "", size)
            pdf.multi_cell(w, size * 0.45, text, align=align, new_x="LMARGIN", new_y="NEXT")

        def pair(left: str, right: str, size: float = 8, bold: bool = False) -> None:
            pdf.set_font(FAMILY, "B" if bold else "", size)
            pdf.cell(w * 0.62, size * 0.45, left, align="L")
            pdf.cell(w * 0.38, size * 0.45, right, align="R", new_x="LMARGIN", new_y="NEXT")

        def rule() -> None:
            pdf.ln(0.8)
            pdf.set_draw_color(120)
            pdf.set_dash_pattern(dash=0.6, gap=0.8)
            pdf.line(m, pdf.get_y(), width - m, pdf.get_y())
            pdf.set_dash_pattern()
            pdf.ln(1.6)

        line(str(shop.get("shop.name", "Super Shop")), 11, True, "C")
        line(str(shop.get("shop.address", "")), 7, align="C")
        line(f"Tel: {shop.get('shop.phone', '')}", 7, align="C")
        if shop.get("shop.bin"):
            line(f"BIN: {shop['shop.bin']}", 7, align="C")
        if shop.get("receipt.header"):
            line(str(shop["receipt.header"]), 7, align="C")
        rule()
        line(f"Invoice: {sale.invoice_number}", 8, True)
        line(f"Date: {_local(db, sale.sale_date)}")
        line(f"Cashier: {sale.cashier.full_name}")
        if sale.customer:
            line(f"Customer: {sale.customer.name}")
        if sale.status == "VOIDED":
            line("*** VOIDED ***", 10, True, "C")
        rule()
        for it in sale.items:
            en, bn = _names(it.product)
            line(en, 8, True)
            if bn:
                line(bn, 7.5)
            pair(f"  {qty(it.quantity)} × {num(it.unit_price)}", num(it.line_total + it.discount_amount))
            if it.discount_amount:
                pair("  ছাড় / Discount", f"-{num(it.discount_amount)}", 7)
        rule()
        pair("Subtotal", num(sale.subtotal))
        if sale.discount_amount:
            pair("Discount", f"-{num(sale.discount_amount)}")
        if shop.get("receipt.show_tax", True) and sale.tax_amount:
            pair("VAT (included)" if shop.get("tax.prices_include_tax", True) else "VAT", num(sale.tax_amount))
        pair("TOTAL / মোট", tk(sale.total_amount), 10, True)
        rule()
        for p in sale.payments:
            pair(p.payment_method.name, num(p.amount))
        if sale.change_amount:
            pair("Change / ফেরত", num(sale.change_amount), 8, True)
        if sale.due_amount:
            pair("DUE (credit) / বাকি", tk(sale.due_amount), 8, True)
        rule()
        line(str(shop.get("receipt.footer", "Thank you!")), 8, align="C")
        return pdf.get_y()

    # pass 1 measures the content on a tall page, pass 2 prints on a roll cut to size
    probe = _new_pdf((width, 1000), margin=3.5)
    probe.set_auto_page_break(False)
    probe.add_page()
    height = draw(probe) + 6
    pdf = _new_pdf((width, max(height, 60)), margin=3.5)
    pdf.set_auto_page_break(False)
    pdf.add_page()
    draw(pdf)
    return _output(pdf)


# ---------------------------------------------------------------- A4 documents

def _header(db: Session, pdf: FPDF, title: str, meta: list[tuple[str, str]]) -> None:
    shop = _shop(db)
    pdf.add_page()
    top = pdf.get_y()
    pdf.set_font(FAMILY, "B", 14)
    pdf.cell(110, 7, str(shop.get("shop.name", "Super Shop")), new_x="LEFT", new_y="NEXT")
    pdf.set_font(FAMILY, "", 8.5)
    for text in (str(shop.get("shop.address", "")), f"Tel {shop.get('shop.phone', '')}", f"BIN {shop['shop.bin']}" if shop.get("shop.bin") else ""):
        if text:
            pdf.cell(110, 4.5, text, new_x="LEFT", new_y="NEXT")
    bottom = pdf.get_y()
    pdf.set_xy(pdf.w - pdf.r_margin - 70, top)
    pdf.set_font(FAMILY, "B", 18)
    pdf.cell(70, 9, title, align="R", new_x="LEFT", new_y="NEXT")
    pdf.set_y(max(bottom, pdf.get_y()) + 5)
    pdf.set_x(pdf.l_margin)
    pdf.set_draw_color(200)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)
    for k, v in meta:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(FAMILY, "B", 9)
        pdf.cell(34, 5.2, k)
        pdf.set_font(FAMILY, "", 9)
        pdf.cell(0, 5.2, v, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def _table(pdf: FPDF, head: list[str], rows: list[list[str]], widths: list[float], right_from: int = 1) -> None:
    aligns = tuple("RIGHT" if i >= right_from else "LEFT" for i in range(len(head)))
    pdf.set_font(FAMILY, "", 8.5)
    heading = FontFace(emphasis="BOLD", color=255, fill_color=(17, 24, 39))
    with pdf.table(
        col_widths=widths, text_align=aligns, line_height=5.2, borders_layout="HORIZONTAL_LINES",
        headings_style=heading, width=sum(widths),
    ) as table:
        table.row(head)
        for r in rows:
            table.row(r)


def _totals(pdf: FPDF, rows: list[tuple[str, str, bool]]) -> None:
    pdf.ln(3)
    for label, value, bold in rows:
        pdf.set_x(pdf.w - pdf.r_margin - 80)
        pdf.set_font(FAMILY, "B" if bold else "", 10 if bold else 9)
        pdf.cell(42, 5.6, label)
        pdf.cell(38, 5.6, value, align=Align.R, new_x="LMARGIN", new_y="NEXT")


def sale_invoice_pdf(db: Session, sale: Sale) -> bytes:
    pdf = _new_pdf()
    pays = ", ".join(f"{p.payment_method.name} {tk(p.amount)}" for p in sale.payments) or "-"
    _header(db, pdf, "INVOICE / চালান", [
        ("Invoice no.", sale.invoice_number), ("Date", _local(db, sale.sale_date)),
        ("Customer", sale.customer.name if sale.customer else "Walk-in customer"), ("Cashier", sale.cashier.full_name),
        ("Payment", pays), ("Status", sale.status)])
    rows = []
    for i, it in enumerate(sale.items, start=1):
        en, bn = _names(it.product)
        rows.append([str(i), f"{en}" + (f" ({bn})" if bn else ""), qty(it.quantity), num(it.unit_price), num(it.discount_amount), num(it.tax_amount), num(it.line_total)])
    _table(pdf, ["#", "Item", "Qty", "Price", "Discount", "VAT", "Total"], rows, [9, 68, 15, 24, 22, 20, 28], right_from=2)
    totals = [("Subtotal", tk(sale.subtotal), False), ("Discount", "-" + tk(sale.discount_amount), False), ("VAT", tk(sale.tax_amount), False),
              ("Total / মোট", tk(sale.total_amount), True), ("Paid", tk(sale.paid_amount), False)]
    if sale.due_amount:
        totals.append(("Balance due / বাকি", tk(sale.due_amount), True))
    _totals(pdf, totals)
    footer = str(_shop(db).get("receipt.footer", ""))
    if footer:
        pdf.ln(10)
        pdf.set_font(FAMILY, "", 9)
        pdf.multi_cell(0, 5, footer, align="C")
    return _output(pdf)


def purchase_invoice_pdf(db: Session, po: PurchaseOrder) -> bytes:
    pdf = _new_pdf()
    _header(db, pdf, "PURCHASE ORDER", [("PO no.", po.po_number), ("Supplier", po.supplier.name), ("Order date", po.order_date.strftime("%d/%m/%Y")), ("Status", po.status)])
    rows = []
    for i, it in enumerate(po.items, start=1):
        en, bn = _names(it.product)
        rows.append([str(i), en + (f" ({bn})" if bn else ""), qty(it.quantity), qty(it.received_quantity), num(it.unit_cost), num(it.discount_amount), num(it.tax_amount), num(it.line_total)])
    _table(pdf, ["#", "Item", "Ordered", "Received", "Unit cost", "Discount", "VAT", "Total"], rows, [8, 56, 16, 16, 22, 20, 18, 26], right_from=2)
    _totals(pdf, [("Subtotal", tk(po.subtotal), False), ("Discount", "-" + tk(po.discount_amount), False), ("VAT", tk(po.tax_amount), False),
                  ("Total", tk(po.total_amount), True), ("Paid", tk(po.paid_amount), False)])
    return _output(pdf)


def _statement(db: Session, title: str, party: str, phone: str | None, rows: list, balance) -> bytes:  # noqa: ANN001
    pdf = _new_pdf()
    _header(db, pdf, title, [("Account", party), ("Phone", phone or "-"), ("Current balance", tk(balance))])
    body = [[_local(db, r.created_at), r.txn_type, r.reference_number or "", num(r.amount), num(r.balance_after)] for r in rows] or [["No transactions", "", "", "", ""]]
    _table(pdf, ["Date", "Type", "Reference", "Amount", "Balance"], body, [40, 26, 50, 32, 32], right_from=3)
    return _output(pdf)


def customer_statement_pdf(db: Session, c: Customer) -> bytes:
    rows = list(db.scalars(select(CustomerTransaction).where(CustomerTransaction.customer_id == c.id).order_by(CustomerTransaction.id).limit(1000)))
    return _statement(db, "CUSTOMER STATEMENT", c.name, c.phone, rows, c.balance)


def supplier_statement_pdf(db: Session, s: Supplier) -> bytes:
    rows = list(db.scalars(select(SupplierTransaction).where(SupplierTransaction.supplier_id == s.id).order_by(SupplierTransaction.id).limit(1000)))
    return _statement(db, "SUPPLIER STATEMENT", s.name, s.phone, rows, s.balance)

