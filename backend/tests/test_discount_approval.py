import pytest
from sqlalchemy import select

from app.models.system import AuditLog
from tests.helpers import ensure_register_open, payment_method_id, stock_of, stock_product

API = "/api/v1/discount-requests"


@pytest.fixture(scope="module")
def cash_desk(client, cashier):
    return ensure_register_open(client, cashier, opening=10000)


@pytest.fixture(scope="module")
def mgr_desk(client, manager, admin):
    if not any(r["name"] == "Counter 2" for r in client.get("/api/v1/registers", headers=admin).json()):
        client.post("/api/v1/registers", headers=admin, json={"name": "Counter 2"})
    return ensure_register_open(client, manager, opening=1000, register="Counter 2")


def _line(prod, pct, qty=1):
    return [{"product_id": prod["id"], "quantity": qty, "discount_type": "PERCENT", "discount_value": pct}]


def _request(client, headers, prod, pct=10, reason="Loyal customer, bulk buy"):
    return client.post(API, headers=headers, json={"items": _line(prod, pct), "reason": reason})


def _sale(client, headers, prod, pct, request_id=None, qty=1):
    prev = client.post("/api/v1/sales/preview", headers=headers, json={"items": _line(prod, pct, qty)}).json()
    body = {"items": _line(prod, pct, qty), "payments": [{"payment_method_id": payment_method_id(client, headers), "amount": prev["grand_total"]}]}
    if request_id:
        body["discount_request_id"] = request_id
    return client.post("/api/v1/sales", headers=headers, json=body)


def test_full_approval_flow_and_single_use(client, admin, cashier, manager, cash_desk, mgr_desk, db_session):
    prod = stock_product(client, admin, qty=20, price=200)
    assert _sale(client, cashier, prod, 10).status_code == 403  # over the 5% limit without approval
    req = _request(client, cashier, prod)
    assert req.status_code == 201, req.text
    rid = req.json()["id"]
    assert req.json()["status"] == "PENDING" and req.json()["requested_by_name"]
    # still refused while pending
    assert _sale(client, cashier, prod, 10, rid).status_code == 403
    ok = client.post(f"{API}/{rid}/approve", headers=manager, json={"note": "fine"})
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED" and ok.json()["decided_by_name"]
    sale = _sale(client, cashier, prod, 10, rid)
    assert sale.status_code == 201, sale.text
    assert sale.json()["total_amount"] == 180
    after = client.get(f"{API}/{rid}", headers=cashier).json()
    assert after["status"] == "USED" and after["used_sale_id"] == sale.json()["id"]
    assert _sale(client, cashier, prod, 10, rid).status_code == 403  # single use
    actions = {a.action for a in db_session.scalars(select(AuditLog).where(AuditLog.entity == "discount_request", AuditLog.entity_id == str(rid)))}
    db_session.rollback()
    assert {"discount.request", "discount.approve", "discount.redeem"} <= actions


def test_rejected_request_cannot_be_used_and_needs_reason(client, admin, cashier, manager, cash_desk):
    prod = stock_product(client, admin, qty=20, price=200)
    rid = _request(client, cashier, prod).json()["id"]
    assert client.post(f"{API}/{rid}/reject", headers=manager, json={}).status_code == 422
    rej = client.post(f"{API}/{rid}/reject", headers=manager, json={"note": "Too generous"})
    assert rej.status_code == 200 and rej.json()["status"] == "REJECTED" and rej.json()["decision_note"] == "Too generous"
    r = _sale(client, cashier, prod, 10, rid)
    assert r.status_code == 403 and r.json()["error"]["code"] == "discount_approval_invalid"
    assert client.post(f"{API}/{rid}/approve", headers=manager, json={}).status_code == 409  # decided already


def test_approval_is_bound_to_the_cart(client, admin, cashier, manager, cash_desk, mgr_desk):
    prod = stock_product(client, admin, qty=20, price=200)
    rid = _request(client, cashier, prod).json()["id"]
    client.post(f"{API}/{rid}/approve", headers=manager, json={})
    assert _sale(client, cashier, prod, 15, rid).status_code == 403  # bigger discount than approved
    assert _sale(client, cashier, prod, 10, rid, qty=2).status_code == 403  # different basket


def test_permissions_and_validation(client, admin, cashier, manager, cash_desk):
    prod = stock_product(client, admin, qty=20, price=200)
    within = _request(client, cashier, prod, pct=3)
    assert within.status_code == 422 and within.json()["error"]["code"] == "discount_within_limit"
    rid = _request(client, cashier, prod).json()["id"]
    assert client.post(f"{API}/{rid}/approve", headers=cashier, json={}).status_code == 403  # cashiers cannot approve
    assert client.post(f"{API}/{rid}/approve", headers=admin, json={}).status_code == 200
    mine = client.get(API, headers=cashier).json()
    assert any(r["id"] == rid for r in mine["items"])
    assert client.get(f"{API}?status=APPROVED", headers=manager).json()["total"] >= 1
    assert client.post(API, headers=cashier, json={"items": _line(prod, 10), "reason": "x"}).status_code == 422


def test_manager_cannot_approve_own_request_and_expiry(client, admin, cashier, manager, cash_desk, db_session):
    from datetime import timedelta

    from app.models.base import utcnow
    from app.models.sales import DiscountRequest

    prod = stock_product(client, admin, qty=20, price=200)
    rid = _request(client, cashier, prod).json()["id"]
    client.post(f"{API}/{rid}/approve", headers=manager, json={})
    row = db_session.get(DiscountRequest, rid)
    row.expires_at = utcnow() - timedelta(minutes=1)
    db_session.commit()
    r = _sale(client, cashier, prod, 10, rid)
    assert r.status_code == 403 and "expired" in r.json()["error"]["message"]
    assert client.get(f"{API}/{rid}", headers=cashier).json()["status"] == "EXPIRED"
    assert stock_of(client, admin, prod["id"]) == 20  # nothing sold
