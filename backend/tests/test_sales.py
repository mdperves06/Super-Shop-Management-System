
import pytest

from tests.helpers import (
    ensure_register_open,
    make_customer,
    payment_method_id,
    sell,
    stock_of,
    stock_product,
)


@pytest.fixture(scope="module")
def cash_desk(client, cashier):
    return ensure_register_open(client, cashier, opening=10000)


@pytest.fixture(scope="module")
def mgr_desk(client, manager, admin):
    if not any(r["name"] == "Counter 2" for r in client.get("/api/v1/registers", headers=admin).json()):
        client.post("/api/v1/registers", headers=admin, json={"name": "Counter 2"})
    return ensure_register_open(client, manager, opening=1000, register="Counter 2")


def test_cannot_sell_without_open_register(client, tokens, admin):
    prod = stock_product(client, admin, qty=10)
    # the staff-like SUPER_ADMIN has no session yet
    r = sell(client, tokens["SUPER_ADMIN"], prod["id"], 1, pay=150)
    assert r.status_code in (403, 409)
    assert r.status_code == 409 and r.json()["error"]["code"] == "register_not_open"


def test_basic_cash_sale_updates_stock_payment_and_profit(client, admin, cashier, cash_desk):
    prod = stock_product(client, admin, qty=100, cost=100, price=150)
    r = sell(client, cashier, prod["id"], 5)
    assert r.status_code == 201, r.text
    sale = r.json()
    assert sale["invoice_number"].startswith("INV-")
    assert sale["total_amount"] == 750 and sale["paid_amount"] == 750 and sale["due_amount"] == 0
    assert stock_of(client, admin, prod["id"]) == 95
    assert sale["payments"][0]["method_type"] == "CASH" and sale["payments"][0]["amount"] == 750
    assert sale["cashier_name"] == "Cashier"
    assert sale["items"][0]["cogs_amount"] is None  # cashier cannot see cost
    full = client.get(f"/api/v1/sales/{sale['id']}", headers=admin).json()
    assert full["cogs_amount"] == 500  # 5 x 100
    moves = client.get("/api/v1/inventory/movements", headers=admin, params={"product_id": prod["id"]}).json()["items"]
    assert moves[0]["txn_type"] == "SALE" and moves[0]["quantity"] == -5 and moves[0]["balance_after"] == 95
    assert moves[0]["reference_type"] == "sale" and moves[0]["reference_id"] == sale["id"]


def test_change_calculation_and_insufficient_payment(client, admin, cashier, cash_desk):
    prod = stock_product(client, admin, qty=20)
    r = sell(client, cashier, prod["id"], 2, pay=1000)  # total 300, tender 1000
    sale = r.json()
    assert r.status_code == 201 and sale["change_amount"] == 700 and sale["paid_amount"] == 300 and sale["tendered_amount"] == 1000
    short = sell(client, cashier, prod["id"], 2, pay=100)
    assert short.status_code == 422 and short.json()["error"]["code"] == "insufficient_payment"
    assert stock_of(client, admin, prod["id"]) == 18  # nothing consumed by the failed attempt
    none = sell(client, cashier, prod["id"], 1, pay=0, payments=[])
    assert none.status_code == 422


def test_split_payment_cash_and_mobile(client, admin, cashier, cash_desk):
    prod = stock_product(client, admin, qty=20, price=500)
    body = {"items": [{"product_id": prod["id"], "quantity": 2}], "payments": [
        {"payment_method_id": payment_method_id(client, cashier, "CASH"), "amount": 500},
        {"payment_method_id": payment_method_id(client, cashier, "BKASH"), "amount": 500, "transaction_id": "TX123"}]}
    r = client.post("/api/v1/sales", headers=cashier, json=body)
    assert r.status_code == 201, r.text
    sale = r.json()
    assert [(p["method_type"], p["amount"]) for p in sale["payments"]] == [("CASH", 500), ("MOBILE", 500)]
    assert sale["paid_amount"] == 1000
    # mobile banking needs a reference
    body["payments"][1].pop("transaction_id")
    assert client.post("/api/v1/sales", headers=cashier, json=body).status_code == 422
    # card / mobile cannot be over-tendered
    body["payments"] = [{"payment_method_id": payment_method_id(client, cashier, "CARD"), "amount": 5000, "reference_number": "X"}]
    r = client.post("/api/v1/sales", headers=cashier, json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "overpayment"


def test_insufficient_stock_and_validation(client, admin, cashier, cash_desk):
    prod = stock_product(client, admin, qty=3)
    r = sell(client, cashier, prod["id"], 4, pay=600)
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    assert stock_of(client, admin, prod["id"]) == 3
    assert sell(client, cashier, prod["id"], 0, pay=1).status_code == 422
    assert sell(client, cashier, prod["id"], -2, pay=1).status_code == 422
    assert client.post("/api/v1/sales", headers=cashier, json={"items": [], "payments": []}).status_code == 422
    assert sell(client, cashier, 999999, 1, pay=1).status_code == 404
    frac = sell(client, cashier, prod["id"], 1.5, pay=300)
    assert frac.status_code == 422  # pieces cannot be fractional


def test_multi_line_sale_rolls_back_completely_on_failure(client, admin, cashier, cash_desk, db_session):
    from sqlalchemy import func, select

    from app.models.sales import Sale

    good = stock_product(client, admin, qty=10)
    scarce = stock_product(client, admin, qty=1)
    before = db_session.scalar(select(func.count()).select_from(Sale))
    db_session.rollback()
    r = sell(client, cashier, good["id"], 0, items=[{"product_id": good["id"], "quantity": 2}, {"product_id": scarce["id"], "quantity": 5}], pay=5000)
    assert r.status_code == 409
    assert stock_of(client, admin, good["id"]) == 10 and stock_of(client, admin, scarce["id"]) == 1
    after = db_session.scalar(select(func.count()).select_from(Sale))
    db_session.rollback()
    assert after == before  # no half-created invoice


def test_discount_limits(client, admin, cashier, manager, cash_desk, mgr_desk):
    prod = stock_product(client, admin, qty=50, price=200)
    line = lambda pct: [{"product_id": prod["id"], "quantity": 1, "discount_type": "PERCENT", "discount_value": pct}]  # noqa: E731
    ok = sell(client, cashier, prod["id"], 1, items=line(5))
    assert ok.status_code == 201 and ok.json()["total_amount"] == 190 and ok.json()["discount_amount"] == 10
    too_much = sell(client, cashier, prod["id"], 1, pay=500, items=line(10))
    assert too_much.status_code == 403 and too_much.json()["error"]["code"] == "discount_limit_exceeded"
    mgr = sell(client, manager, prod["id"], 1, items=line(10))
    assert mgr.status_code == 201 and mgr.json()["total_amount"] == 180
    # preview tells the POS whether the discount would be accepted
    prev = client.post("/api/v1/sales/preview", headers=cashier, json={"items": line(10)}).json()
    assert prev["discount_allowed"] is False and prev["max_discount_percent"] == 5
    # invoice-level fixed discount is spread across lines and counted against the cap
    inv = client.post("/api/v1/sales/preview", headers=manager, json={"items": [{"product_id": prod["id"], "quantity": 2}], "invoice_discount_type": "FIXED", "invoice_discount_value": 40}).json()
    assert inv["grand_total"] == 360 and inv["lines"][0]["invoice_discount"] == 40


def test_spec_profit_example_with_discount(client, admin, cashier, manager, mgr_desk):
    """price 150, cost 100, qty 10 => revenue 1500, COGS 1000, profit 500; with 100 discount => 1400 / 400."""
    prod = stock_product(client, admin, qty=50, cost=100, price=150)
    r = sell(client, manager, prod["id"], 10, invoice_discount_type="FIXED", invoice_discount_value=100)
    assert r.status_code == 201, r.text
    sale = client.get(f"/api/v1/sales/{r.json()['id']}", headers=admin).json()
    assert sale["subtotal"] == 1500 and sale["discount_amount"] == 100 and sale["total_amount"] == 1400
    assert sale["cogs_amount"] == 1000
    assert sale["total_amount"] - sale["tax_amount"] - sale["cogs_amount"] == 400


def test_vat_inclusive_pricing(client, admin, cashier, cash_desk):
    tax = next(t for t in client.get("/api/v1/tax-rates", headers=admin).json() if t["name"] == "VAT 15%")
    prod = stock_product(client, admin, qty=10, price=115, tax_rate_id=tax["id"])
    r = sell(client, cashier, prod["id"], 1)
    sale = r.json()
    assert sale["total_amount"] == 115 and sale["tax_amount"] == 15  # 115 incl. 15% VAT => 100 + 15


def test_credit_sale_rules(client, admin, cashier, manager, mgr_desk, cash_desk):
    prod = stock_product(client, admin, qty=50, price=1000)
    cust = make_customer(client, admin, credit_limit=3000)
    cash = payment_method_id(client, admin, "CASH")
    body = {"items": [{"product_id": prod["id"], "quantity": 3}], "customer_id": cust["id"], "payments": [{"payment_method_id": cash, "amount": 1000}]}
    # cashiers cannot sell on credit
    r = client.post("/api/v1/sales", headers=cashier, json=body)
    assert r.status_code == 403 and r.json()["error"]["code"] == "credit_not_permitted"
    # guests cannot buy on credit
    g = client.post("/api/v1/sales", headers=manager, json={**body, "customer_id": None})
    assert g.status_code == 422 and g.json()["error"]["code"] == "insufficient_payment"
    ok = client.post("/api/v1/sales", headers=manager, json=body)
    assert ok.status_code == 201, ok.text
    sale = ok.json()
    assert sale["total_amount"] == 3000 and sale["paid_amount"] == 1000 and sale["due_amount"] == 2000
    c = client.get(f"/api/v1/customers/{cust['id']}", headers=admin).json()
    assert c["balance"] == 2000
    # limit is 3000 so another 1500 unpaid must fail
    over = client.post("/api/v1/sales", headers=manager, json={"items": [{"product_id": prod["id"], "quantity": 2}], "customer_id": cust["id"], "payments": [{"payment_method_id": cash, "amount": 500}]})
    assert over.status_code == 422 and over.json()["error"]["code"] == "credit_limit_exceeded"
    # customer settles part of the balance
    p = client.post(f"/api/v1/customers/{cust['id']}/payments", headers=admin, json={"amount": 1500, "payment_method_id": cash})
    assert p.status_code == 201
    assert client.get(f"/api/v1/customers/{cust['id']}", headers=admin).json()["balance"] == 500
    ledger = client.get(f"/api/v1/customers/{cust['id']}/ledger", headers=admin).json()["items"]
    assert [(r["txn_type"], r["amount"], r["balance_after"]) for r in ledger] == [("PAYMENT", -1500, 500), ("PAYMENT", -1000, 2000), ("SALE", 3000, 3000)]
    assert client.post(f"/api/v1/customers/{cust['id']}/payments", headers=admin, json={"amount": 999, "payment_method_id": cash}).status_code == 422


def test_return_restocks_and_refunds(client, admin, cashier, cash_desk):
    prod = stock_product(client, admin, qty=100, cost=100, price=150)
    sale = sell(client, cashier, prod["id"], 5).json()
    assert stock_of(client, admin, prod["id"]) == 95
    item = sale["items"][0]
    cash = payment_method_id(client, admin, "CASH")
    r = client.post("/api/v1/sale-returns", headers=cashier, json={"sale_id": sale["id"], "reason": "customer changed mind", "refund_method_id": cash, "items": [{"sale_item_id": item["id"], "quantity": 2}]})
    assert r.status_code == 201, r.text
    ret = r.json()
    assert ret["total_amount"] == 300 and ret["refunded_amount"] == 300 and ret["return_number"].startswith("RET-")
    assert stock_of(client, admin, prod["id"]) == 97
    full = client.get(f"/api/v1/sales/{sale['id']}", headers=admin).json()
    assert full["return_status"] == "PARTIAL" and full["returned_amount"] == 300
    assert full["total_amount"] == 750  # the original invoice is never edited
    over = client.post("/api/v1/sale-returns", headers=cashier, json={"sale_id": sale["id"], "reason": "again", "refund_method_id": cash, "items": [{"sale_item_id": item["id"], "quantity": 4}]})
    assert over.status_code == 422 and over.json()["error"]["code"] == "over_return"
    rest = client.post("/api/v1/sale-returns", headers=cashier, json={"sale_id": sale["id"], "reason": "rest", "refund_method_id": cash, "items": [{"sale_item_id": item["id"], "quantity": 3}]})
    assert rest.json()["total_amount"] == 450
    assert client.get(f"/api/v1/sales/{sale['id']}", headers=admin).json()["return_status"] == "FULL"
    assert stock_of(client, admin, prod["id"]) == 100
    moves = client.get("/api/v1/inventory/movements", headers=admin, params={"product_id": prod["id"]}).json()["items"]
    assert [m["txn_type"] for m in moves[:3]] == ["SALE_RETURN", "SALE_RETURN", "SALE"]
    no_method = client.post("/api/v1/sale-returns", headers=cashier, json={"sale_id": sale["id"], "reason": "x y z", "items": [{"sale_item_id": item["id"], "quantity": 1}]})
    assert no_method.status_code in (409, 422)


def test_return_of_credit_sale_reduces_due_first(client, admin, manager, mgr_desk):
    prod = stock_product(client, admin, qty=20, price=1000)
    cust = make_customer(client, admin, credit_limit=10000)
    cash = payment_method_id(client, admin, "CASH")
    sale = client.post("/api/v1/sales", headers=manager, json={"items": [{"product_id": prod["id"], "quantity": 4}], "customer_id": cust["id"], "payments": [{"payment_method_id": cash, "amount": 1000}]}).json()
    assert sale["due_amount"] == 3000
    item = sale["items"][0]
    # return 2 units (value 2000): all of it comes off the unpaid balance, nothing paid out
    r = client.post("/api/v1/sale-returns", headers=manager, json={"sale_id": sale["id"], "reason": "wrong size", "refund_method_id": cash, "items": [{"sale_item_id": item["id"], "quantity": 2}]}).json()
    assert r["due_reduced"] == 2000 and r["refunded_amount"] == 0
    assert client.get(f"/api/v1/customers/{cust['id']}", headers=admin).json()["balance"] == 1000
    # return remaining 2 (value 2000): 1000 due left, 1000 refunded
    r2 = client.post("/api/v1/sale-returns", headers=manager, json={"sale_id": sale["id"], "reason": "rest", "refund_method_id": cash, "items": [{"sale_item_id": item["id"], "quantity": 2}]}).json()
    assert r2["due_reduced"] == 1000 and r2["refunded_amount"] == 1000
    assert client.get(f"/api/v1/customers/{cust['id']}", headers=admin).json()["balance"] == 0


def test_void_sale_reverses_everything(client, admin, cashier, manager, cash_desk, mgr_desk):
    prod = stock_product(client, admin, qty=10)
    sale = sell(client, manager, prod["id"], 4).json()
    assert stock_of(client, admin, prod["id"]) == 6
    # cashiers cannot void
    assert client.post(f"/api/v1/sales/{sale['id']}/void", headers=cashier, json={"reason": "oops mistake"}).status_code == 403
    assert client.post(f"/api/v1/sales/{sale['id']}/void", headers=manager, json={"reason": "x"}).status_code == 422
    r = client.post(f"/api/v1/sales/{sale['id']}/void", headers=manager, json={"reason": "entered wrong item"})
    assert r.status_code == 200 and r.json()["status"] == "VOIDED"
    assert stock_of(client, admin, prod["id"]) == 10
    assert client.post(f"/api/v1/sales/{sale['id']}/void", headers=manager, json={"reason": "again please"}).status_code == 409
    logs = client.get("/api/v1/audit-logs", headers=admin, params={"entity": "sale", "entity_id": sale["id"]}).json()["items"]
    assert "sale.void" in [e["action"] for e in logs]
    ret = client.post("/api/v1/sale-returns", headers=manager, json={"sale_id": sale["id"], "reason": "no way", "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": 1}]})
    assert ret.status_code == 409


def test_idempotent_client_ref(client, admin, cashier, cash_desk):
    prod = stock_product(client, admin, qty=10)
    body = {"items": [{"product_id": prod["id"], "quantity": 1}], "client_ref": "ref-abc-123",
            "payments": [{"payment_method_id": payment_method_id(client, admin, "CASH"), "amount": 150}]}
    a = client.post("/api/v1/sales", headers=cashier, json=body).json()
    b = client.post("/api/v1/sales", headers=cashier, json=body).json()
    assert a["id"] == b["id"] and stock_of(client, admin, prod["id"]) == 9


def test_cashier_only_sees_own_sales(client, admin, cashier, manager, cash_desk, mgr_desk):
    prod = stock_product(client, admin, qty=10)
    mine = sell(client, cashier, prod["id"], 1).json()
    theirs = sell(client, manager, prod["id"], 1).json()
    ids = {s["id"] for s in client.get("/api/v1/sales", headers=cashier, params={"page_size": 200}).json()["items"]}
    assert mine["id"] in ids and theirs["id"] not in ids
    assert client.get(f"/api/v1/sales/{theirs['id']}", headers=cashier).status_code == 403
    all_ids = {s["id"] for s in client.get("/api/v1/sales", headers=admin, params={"page_size": 200}).json()["items"]}
    assert {mine["id"], theirs["id"]} <= all_ids


def test_promotions_apply_automatically(client, admin, cashier, cash_desk):
    prod = stock_product(client, admin, qty=50, price=100)
    r = client.post("/api/v1/promotions", headers=admin, json={"name": "Buy 2 get 1", "promo_type": "BUY_X_GET_Y", "product_id": prod["id"], "buy_quantity": 2, "get_quantity": 1})
    assert r.status_code == 201, r.text
    prev = client.post("/api/v1/sales/preview", headers=cashier, json={"items": [{"product_id": prod["id"], "quantity": 3}]}).json()
    assert prev["grand_total"] == 200 and prev["lines"][0]["promotion"] == "Buy 2 get 1"
    prev = client.post("/api/v1/sales/preview", headers=cashier, json={"items": [{"product_id": prod["id"], "quantity": 2}]}).json()
    assert prev["grand_total"] == 200  # not enough for the free unit
    assert client.post("/api/v1/promotions", headers=cashier, json={"name": "x", "promo_type": "PERCENT_OFF", "product_id": prod["id"], "value": 5}).status_code == 403


def test_time_window_promotion(client, admin, cashier, cash_desk):
    prod = stock_product(client, admin, qty=50, price=100)
    # day-of-week list that excludes every day but is syntactically valid is impossible, so use a window in the past
    client.post("/api/v1/promotions", headers=admin, json={"name": "Old", "promo_type": "PERCENT_OFF", "product_id": prod["id"], "value": 50, "end_at": "2020-01-01T00:00:00Z"})
    prev = client.post("/api/v1/sales/preview", headers=cashier, json={"items": [{"product_id": prod["id"], "quantity": 1}]}).json()
    assert prev["grand_total"] == 100
    client.post("/api/v1/promotions", headers=admin, json={"name": "Live", "promo_type": "PERCENT_OFF", "product_id": prod["id"], "value": 10, "start_time": "00:00", "end_time": "23:59"})
    prev = client.post("/api/v1/sales/preview", headers=cashier, json={"items": [{"product_id": prod["id"], "quantity": 1}]}).json()
    assert prev["grand_total"] == 90


def test_sold_expired_stock_is_blocked(client, admin, cashier, cash_desk, db_session):
    from datetime import date, timedelta

    from sqlalchemy import update

    from app.models.inventory import InventoryBatch

    prod = stock_product(client, admin, qty=10, track_expiry=True)
    db_session.execute(update(InventoryBatch).where(InventoryBatch.product_id == prod["id"]).values(expiry_date=date.today() - timedelta(days=1)))
    db_session.commit()
    r = sell(client, cashier, prod["id"], 1, pay=150)
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    exp = client.get("/api/v1/inventory/expired", headers=admin).json()
    assert any(b["product_id"] == prod["id"] for b in exp["items"])
