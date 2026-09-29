from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.deps import DB, has_permission, require
from app.core.errors import PermissionDenied
from app.models.auth import User
from app.services import payment_service, pdf_service, purchase_service, sales_service
from app.api.v1.customers import get_customer

router = APIRouter(prefix="/documents", tags=["documents"])


def _pdf(data: bytes, name: str) -> Response:
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


def _own_sale(db: DB, user: User, sale_id: int):  # noqa: ANN202
    sale = sales_service.get_sale(db, sale_id)
    if not has_permission(user, "sale.read_all") and sale.cashier_id != user.id:
        raise PermissionDenied("You can only print your own sales")
    return sale


@router.get("/sales/{sale_id}/receipt.pdf")
def receipt(sale_id: int, db: DB, user: Annotated[User, Depends(require("sale.read"))]):
    sale = _own_sale(db, user, sale_id)
    return _pdf(pdf_service.receipt_pdf(db, sale), f"receipt-{sale.invoice_number}")


@router.get("/sales/{sale_id}/invoice.pdf")
def invoice(sale_id: int, db: DB, user: Annotated[User, Depends(require("sale.read"))]):
    sale = _own_sale(db, user, sale_id)
    return _pdf(pdf_service.sale_invoice_pdf(db, sale), sale.invoice_number)


@router.get("/purchases/{purchase_id}/invoice.pdf")
def purchase_invoice(purchase_id: int, db: DB, _: Annotated[User, Depends(require("purchase.read"))]):
    po = purchase_service.get_purchase(db, purchase_id)
    return _pdf(pdf_service.purchase_invoice_pdf(db, po), po.po_number)


@router.get("/customers/{customer_id}/statement.pdf")
def customer_statement(customer_id: int, db: DB, _: Annotated[User, Depends(require("customer.read"))]):
    c = get_customer(db, customer_id)
    return _pdf(pdf_service.customer_statement_pdf(db, c), f"statement-{c.code}")


@router.get("/suppliers/{supplier_id}/statement.pdf")
def supplier_statement(supplier_id: int, db: DB, _: Annotated[User, Depends(require("supplier.read"))]):
    s = payment_service.require_supplier(db, supplier_id)
    return _pdf(pdf_service.supplier_statement_pdf(db, s), f"statement-{s.code}")
