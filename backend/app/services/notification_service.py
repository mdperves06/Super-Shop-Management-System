from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.catalog import Product
from app.models.customers import Customer
from app.models.inventory import Inventory
from app.models.purchasing import PurchaseOrder, Supplier
from app.models.system import Notification, NotificationRead
from app.services import inventory_queries, settings_service


def notify(
    db: Session, *, type: str, title: str, message: str, severity: str = "info", permission: str | None = None,
    entity: str | None = None, entity_id: int | str | None = None, dedupe_key: str | None = None,
) -> Notification | None:
    """Create a notification; a repeated dedupe_key is silently ignored so alerts don't spam."""
    if dedupe_key and db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe_key)):
        return None
    row = Notification(
        type=type, title=title, message=message, severity=severity, required_permission=permission, entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None, dedupe_key=dedupe_key,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        return None
    return row


def refresh_alerts(db: Session) -> int:
    """Scan stock, expiry, payables and receivables; one notification per condition per day."""
    today = date.today().isoformat()
    created = 0

    def add(**kw) -> None:  # noqa: ANN003
        nonlocal created
        if notify(db, **kw):
            created += 1

    low = db.execute(
        select(Product.id, Product.name, Product.sku, Inventory.current_stock, Product.reorder_level)
        .join(Inventory, Inventory.product_id == Product.id)
        .where(*inventory_queries.low_stock_filter()).limit(200)).all()
    for pid, name, sku, stock, reorder in low:
        add(type="low_stock", severity="warning", title=f"Low stock: {name}",
            message=f"{name} ({sku}) has {stock:g} left; reorder level is {reorder:g}.",
            permission="inventory.read", entity="product", entity_id=pid, dedupe_key=f"low:{pid}:{today}")
    out = db.execute(
        select(Product.id, Product.name, Product.sku).join(Inventory, Inventory.product_id == Product.id)
        .where(*inventory_queries.out_of_stock_filter()).limit(200)).all()
    for pid, name, sku in out:
        add(type="out_of_stock", severity="critical", title=f"Out of stock: {name}",
            message=f"{name} ({sku}) is out of stock.", permission="inventory.read", entity="product",
            entity_id=pid, dedupe_key=f"out:{pid}:{today}")

    days = int(settings_service.get(db, "inventory.expiry_warning_days"))
    for b in db.scalars(inventory_queries.expiring_batches_stmt(days).limit(200)).all():
        left = (b.expiry_date - date.today()).days
        add(type="expiring", severity="warning", title=f"Expiring soon: {b.product.name}",
            message=f"Batch {b.batch_number} of {b.product.name} ({b.quantity_remaining:g} units) expires in {left} day(s).",
            permission="inventory.read", entity="batch", entity_id=b.id, dedupe_key=f"exp:{b.id}:{today}")
    for b in db.scalars(inventory_queries.expired_batches_stmt().limit(200)).all():
        add(type="expired", severity="critical", title=f"Expired stock: {b.product.name}",
            message=f"Batch {b.batch_number} of {b.product.name} ({b.quantity_remaining:g} units) expired on {b.expiry_date}.",
            permission="inventory.read", entity="batch", entity_id=b.id, dedupe_key=f"expd:{b.id}")

    for po in db.scalars(select(PurchaseOrder).where(PurchaseOrder.status == "PENDING").limit(50)).all():
        add(type="pending_purchase", severity="info", title=f"Purchase awaiting approval: {po.po_number}",
            message=f"{po.po_number} from {po.supplier.name} (৳{po.total_amount:,.2f}) is waiting for approval.",
            permission="purchase.approve", entity="purchase", entity_id=po.id, dedupe_key=f"pend:{po.id}")

    for s in db.scalars(select(Supplier).where(Supplier.balance > 0, Supplier.is_deleted.is_(False)).limit(50)).all():
        add(type="supplier_due", severity="info", title=f"Supplier payable: {s.name}",
            message=f"We owe {s.name} ৳{s.balance:,.2f}.", permission="supplier.payment", entity="supplier",
            entity_id=s.id, dedupe_key=f"sdue:{s.id}:{today[:7]}")
    for c in db.scalars(select(Customer).where(Customer.balance > 0, Customer.is_deleted.is_(False)).limit(50)).all():
        add(type="payment_due", severity="info", title=f"Customer payment due: {c.name}",
            message=f"{c.name} owes ৳{c.balance:,.2f}.", permission="customer.payment", entity="customer",
            entity_id=c.id, dedupe_key=f"cdue:{c.id}:{today[:7]}")
    return created


def visible_query(user: User):  # noqa: ANN201
    codes = user.permission_codes
    return select(Notification).where(
        (Notification.required_permission.is_(None)) | (Notification.required_permission.in_(codes or {""}))
    )


def unread_count(db: Session, user: User) -> int:
    sub = visible_query(user).subquery()
    read = select(NotificationRead.notification_id).where(NotificationRead.user_id == user.id)
    return db.scalar(select(func.count()).select_from(sub).where(sub.c.id.not_in(read))) or 0
