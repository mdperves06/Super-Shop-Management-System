from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.api.deps import DB, CurrentUser, Pagination, require
from app.core.errors import NotFoundError
from app.models.auth import Employee, User
from app.models.catalog import Product, ProductBarcode
from app.models.customers import Customer
from app.models.purchasing import Supplier
from app.models.sales import Sale
from app.models.system import Notification, NotificationRead
from app.repositories.base import like, page_response, paginate
from app.schemas.common import Message, Page, UTCDateTime
from app.services import dashboard_service, export_service, notification_service, report_service

router = APIRouter(tags=["analytics"])


# ---- dashboard ------------------------------------------------------------------------

@router.get("/dashboard")
def dashboard(db: DB, user: Annotated[User, Depends(require("dashboard.view"))], period: str = "today", start: date | None = None,
              end: date | None = None, top_n: int = 10, granularity: str | None = None):
    return dashboard_service.build(db, user, period, start, end, top_n, granularity)


# ---- reports --------------------------------------------------------------------------

@router.get("/reports")
def report_catalog(user: CurrentUser):
    codes = user.permission_codes
    return [{"name": n, "permission": s.permission} for n, s in report_service.REGISTRY.items() if s.permission in codes]


@router.get("/reports/{name}")
def run_report(
    name: str, db: DB, user: CurrentUser, format: Annotated[str, Query(pattern="^(json|csv|xlsx)$")] = "json",
    period: str | None = None, start: date | None = None, end: date | None = None, product_id: int | None = None,
    category_id: int | None = None, supplier_id: int | None = None, employee_id: int | None = None,
    payment_method_id: int | None = None, customer_id: int | None = None, group_by: str = "day", days: int | None = None,
    limit: int = 500,
):
    spec = report_service.REGISTRY.get(name)
    if spec is None:
        raise NotFoundError(f"Unknown report '{name}'")
    from app.core.errors import PermissionDenied

    if spec.permission not in user.permission_codes:
        raise PermissionDenied("You do not have access to this report", details={"required": [spec.permission]})
    if format != "json" and "report.export" not in user.permission_codes:
        raise PermissionDenied("You do not have permission to export reports", details={"required": ["report.export"]})
    report, _ = report_service.run(db, name, user, period=period, start=start, end=end, product_id=product_id, category_id=category_id,
                                   supplier_id=supplier_id, employee_id=employee_id, payment_method_id=payment_method_id,
                                   customer_id=customer_id, group_by=group_by, days=days, limit=min(max(limit, 1), 5000))
    if format == "json":
        return {"title": report.title, "columns": report.columns, "rows": report.rows, "summary": report.summary, "period": report.period}
    data, media = export_service.render(report, format)
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}.{format}"'})


@router.get("/exports/{dataset}")
def export_dataset(dataset: str, db: DB, user: CurrentUser, format: Annotated[str, Query(pattern="^(csv|xlsx)$")] = "csv"):
    from app.core.errors import PermissionDenied

    needed = export_service.EXPORT_PERMISSIONS.get(dataset)
    if needed is None:
        raise NotFoundError(f"Unknown dataset '{dataset}'")
    codes = user.permission_codes
    if needed not in codes or ("report.export" not in codes and "import.manage" not in codes):
        raise PermissionDenied("You do not have permission to export this data", details={"required": [needed, "report.export"]})
    report = export_service.dataset(db, dataset, user)
    data, media = export_service.render(report, format)
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{dataset}.{format}"'})


# ---- notifications --------------------------------------------------------------------

class NotificationOut(BaseModel):
    id: int
    type: str
    severity: str
    title: str
    message: str
    entity: str | None
    entity_id: str | None
    created_at: UTCDateTime
    is_read: bool


@router.get("/notifications", response_model=Page[NotificationOut])
def list_notifications(db: DB, p: Pagination, user: Annotated[User, Depends(require("notification.read"))], unread_only: bool = False, type: str | None = None):
    notification_service.refresh_alerts(db)
    db.commit()
    read_ids = set(db.scalars(select(NotificationRead.notification_id).where(NotificationRead.user_id == user.id)))
    stmt = notification_service.visible_query(user)
    if type:
        stmt = stmt.where(Notification.type == type)
    if unread_only and read_ids:
        stmt = stmt.where(Notification.id.not_in(read_ids))
    rows, total = paginate(db, stmt.order_by(Notification.id.desc()), p)
    return page_response([NotificationOut(id=n.id, type=n.type, severity=n.severity, title=n.title, message=n.message, entity=n.entity,
                                          entity_id=n.entity_id, created_at=n.created_at, is_read=n.id in read_ids) for n in rows], total, p)


@router.get("/notifications/unread-count")
def unread_count(db: DB, user: Annotated[User, Depends(require("notification.read"))]):
    return {"count": notification_service.unread_count(db, user)}


@router.post("/notifications/{notification_id}/read", response_model=Message)
def mark_read(notification_id: int, db: DB, user: Annotated[User, Depends(require("notification.read"))]):
    if not db.get(Notification, notification_id):
        raise NotFoundError("Notification not found")
    if not db.get(NotificationRead, (notification_id, user.id)):
        db.add(NotificationRead(notification_id=notification_id, user_id=user.id))
    db.commit()
    return Message(message="Marked as read")


@router.post("/notifications/read-all", response_model=Message)
def mark_all_read(db: DB, user: Annotated[User, Depends(require("notification.read"))]):
    read = select(NotificationRead.notification_id).where(NotificationRead.user_id == user.id)
    ids = db.scalars(notification_service.visible_query(user).with_only_columns(Notification.id).where(Notification.id.not_in(read))).all()
    db.add_all(NotificationRead(notification_id=i, user_id=user.id) for i in ids)
    db.commit()
    return Message(message=f"{len(ids)} notification(s) marked as read")


# ---- global search --------------------------------------------------------------------

@router.get("/search")
def global_search(db: DB, user: CurrentUser, q: str = Query(min_length=1, max_length=100), limit: int = 5):
    limit = min(max(limit, 1), 10)
    t = like(q.strip())
    codes = user.permission_codes
    out: dict[str, list[dict[str, Any]]] = {}
    if "product.read" in codes:
        rows = db.scalars(select(Product).where(Product.is_deleted.is_(False), or_(
            Product.name.ilike(t, escape="\\"), Product.name_bn.ilike(t, escape="\\"), Product.sku.ilike(t, escape="\\"),
            Product.barcodes.any(ProductBarcode.barcode.ilike(t, escape="\\")))).order_by(Product.name).limit(limit)).unique()
        out["products"] = [{"id": p.id, "title": p.name, "subtitle": f"{p.sku} · stock {p.current_stock:g}", "href": f"/products/{p.id}"} for p in rows]
    if "customer.read" in codes:
        rows = db.scalars(select(Customer).where(Customer.is_deleted.is_(False), or_(Customer.name.ilike(t, escape="\\"), Customer.phone.ilike(t, escape="\\"))).limit(limit))
        out["customers"] = [{"id": c.id, "title": c.name, "subtitle": c.phone or c.code, "href": f"/customers/{c.id}"} for c in rows]
    if "supplier.read" in codes:
        rows = db.scalars(select(Supplier).where(Supplier.is_deleted.is_(False), or_(Supplier.name.ilike(t, escape="\\"), Supplier.company.ilike(t, escape="\\"), Supplier.phone.ilike(t, escape="\\"))).limit(limit))
        out["suppliers"] = [{"id": s.id, "title": s.name, "subtitle": s.phone or s.code, "href": f"/suppliers/{s.id}"} for s in rows]
    if "sale.read" in codes:
        stmt = select(Sale).where(Sale.invoice_number.ilike(t, escape="\\")).order_by(Sale.id.desc()).limit(limit)
        if "sale.read_all" not in codes:
            stmt = stmt.where(Sale.cashier_id == user.id)
        out["sales"] = [{"id": s.id, "title": s.invoice_number, "subtitle": f"৳{s.total_amount:,.2f} · {s.status}", "href": f"/sales/{s.id}"} for s in db.scalars(stmt).unique()]
    if "employee.read" in codes:
        rows = db.scalars(select(Employee).where(Employee.is_deleted.is_(False), or_(Employee.employee_code.ilike(t, escape="\\"), Employee.full_name.ilike(t, escape="\\"))).limit(limit)).unique()
        out["employees"] = [{"id": e.id, "title": e.full_name, "subtitle": e.employee_code, "href": f"/employees/{e.id}"} for e in rows]
    return {k: v for k, v in out.items() if v}
