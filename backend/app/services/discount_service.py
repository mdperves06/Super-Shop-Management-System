"""Manager approval for discounts above a cashier's limit.

cashier POST request -> PENDING -> manager approves/rejects -> APPROVED -> redeemed by exactly one sale -> USED.
An approval is bound to the exact cart (products, quantities, discounts, customer) and to the requester, and it
expires, so it cannot be reused or carried over to a different basket.
"""

import hashlib
import json
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.models.auth import User
from app.models.base import utcnow
from app.models.sales import DiscountRequest
from app.schemas.sales import CartIn, DiscountRequestIn
from app.services import audit, notification_service, sales_service

TTL = timedelta(minutes=30)


def cart_fingerprint(data: CartIn) -> tuple[str, dict]:
    snap = {
        "customer_id": data.customer_id,
        "invoice_discount_type": data.invoice_discount_type,
        "invoice_discount_value": str(Decimal(data.invoice_discount_value).normalize()),
        "items": sorted(
            (
                {"product_id": i.product_id, "quantity": str(Decimal(i.quantity).normalize()), "discount_type": i.discount_type,
                 "discount_value": str(Decimal(i.discount_value).normalize())}
                for i in data.items
            ),
            key=lambda x: (x["product_id"], x["quantity"], x["discount_type"] or "", x["discount_value"]),
        ),
    }
    return hashlib.sha256(json.dumps(snap, sort_keys=True).encode()).hexdigest(), snap


def get(db: Session, request_id: int, *, lock: bool = False) -> DiscountRequest:
    stmt = select(DiscountRequest).where(DiscountRequest.id == request_id)
    if lock:
        stmt = stmt.with_for_update(of=DiscountRequest)
    row = db.scalars(stmt).unique().first()
    if not row:
        raise NotFoundError("Discount request not found")
    return row


def effective_status(row: DiscountRequest) -> str:
    return "EXPIRED" if row.status in ("PENDING", "APPROVED") and row.expires_at < utcnow() else row.status


def create(db: Session, data: DiscountRequestIn, user: User) -> DiscountRequest:
    cart, _ = sales_service.build_cart(db, data)
    allowed, cap = sales_service.check_discount_allowed(db, cart, user)
    if allowed:
        raise ValidationFailed("This discount is within your limit; no approval is needed", code="discount_within_limit")
    digest, snap = cart_fingerprint(data)
    row = DiscountRequest(
        requested_by=user.id, cart_hash=digest, cart_snapshot=snap, discount_percent=cart.manual_discount_percent,
        discount_amount=cart.manual_discount_total, reason=data.reason.strip(), status="PENDING", expires_at=utcnow() + TTL,
    )
    db.add(row)
    db.flush()
    audit.record(db, user=user, action="discount.request", entity="discount_request", entity_id=row.id,
                 new={"percent": row.discount_percent, "amount": row.discount_amount, "limit": cap, "reason": row.reason})
    notification_service.notify(
        db, type="discount_request", severity="warning", title="Discount approval needed",
        message=f"{user.full_name} asks for a {row.discount_percent}% discount (৳{row.discount_amount:,.2f}): {row.reason}",
        permission="discount.approve", entity="discount_request", entity_id=row.id, dedupe_key=f"discreq:{row.id}")
    return row


def decide(db: Session, request_id: int, *, approve: bool, note: str | None, user: User) -> DiscountRequest:
    row = get(db, request_id, lock=True)
    if row.requested_by == user.id:
        raise PermissionDenied("You cannot decide your own discount request", code="self_approval")
    if row.status != "PENDING":
        raise ConflictError(f"This request is already {row.status.lower()}", code="already_decided")
    if row.expires_at < utcnow():
        raise ConflictError("This request has expired; ask the cashier to submit it again", code="request_expired")
    if not approve and not (note and note.strip()):
        raise ValidationFailed("A reason is required to reject a request", code="note_required")
    row.status = "APPROVED" if approve else "REJECTED"
    row.decided_by, row.decided_at, row.decision_note = user.id, utcnow(), (note or "").strip() or None
    audit.record(db, user=user, action="discount.approve" if approve else "discount.reject", entity="discount_request",
                 entity_id=row.id, new={"requested_by": row.requested_by, "percent": row.discount_percent, "note": row.decision_note})
    db.flush()
    return row


def validate_for_sale(db: Session, request_id: int, data: CartIn, user: User) -> DiscountRequest:
    """Checks an approval may cover this sale; the caller redeems it with `redeem` once the sale exists."""
    row = get(db, request_id)
    bad = None
    if row.requested_by != user.id:
        bad = "This approval belongs to another cashier"
    elif row.status != "APPROVED":
        bad = f"This discount request is {effective_status(row).lower()}, not approved"
    elif row.expires_at < utcnow():
        bad = "This discount approval has expired"
    elif row.cart_hash != cart_fingerprint(data)[0]:
        bad = "The cart changed after the discount was approved; request approval again"
    if bad:
        raise PermissionDenied(bad, code="discount_approval_invalid")
    return row


def redeem(db: Session, row: DiscountRequest, sale_id: int, user: User) -> None:
    """Single-use: the conditional UPDATE lets exactly one concurrent sale win."""
    res = db.execute(
        update(DiscountRequest).where(DiscountRequest.id == row.id, DiscountRequest.status == "APPROVED")
        .values(status="USED", used_sale_id=sale_id)
    )
    if res.rowcount != 1:
        raise ConflictError("This discount approval was already used", code="discount_approval_used")
    audit.record(db, user=user, action="discount.redeem", entity="discount_request", entity_id=row.id, new={"sale_id": sale_id})
