from decimal import Decimal

from tests.conftest import PASSWORD
from tests.helpers import make_customer, payment_method_id, sell, stock_product, uid


def _new_user(client, admin, role_name):
    roles = {r["name"]: r["id"] for r in client.get("/api/v1/roles", headers=admin).json()}
    email = f"{role_name.lower()}{uid()}@example.com"
    r = client.post("/api/v1/users", headers=admin, json={"email": email, "full_name": f"{role_name} {uid()}", "password": PASSWORD, "role_ids": [roles[role_name]]})
    assert r.status_code == 201, r.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()
    return {"Authorization": f"Bearer {login['access_token']}"}, r.json()


def test_cash_register_reconciliation_with_discrepancy(client, admin):
    """opening 10,000 + cash sales 5,000 - cash expense 1,000 = expected 14,000; counted 13,500 => -500."""
    mgr, _ = _new_user(client, admin, "MANAGER")
    reg = client.post("/api/v1/registers", headers=admin, json={"name": f"Counter {uid()}"}).json()
    s = client.post("/api/v1/cash-sessions/open", headers=mgr, json={"register_id": reg["id"], "opening_cash": 10000})
    assert s.status_code == 201, s.text
    session = s.json()
    # the same user cannot open a second session, nor can the register be shared
    assert client.post("/api/v1/cash-sessions/open", headers=mgr, json={"register_id": reg["id"], "opening_cash": 1}).status_code == 409

    prod = stock_product(client, admin, qty=100, price=100)
    assert sell(client, mgr, prod["id"], 50, pay=5000).status_code == 201
    # a mobile-banking sale must NOT count towards the drawer
    assert sell(client, mgr, prod["id"], 2, pay=200, method="BKASH", payments=[{"payment_method_id": payment_method_id(client, mgr, "BKASH"), "amount": 200, "transaction_id": "T1"}]).status_code == 201
    cat = client.get("/api/v1/expense-categories", headers=admin).json()[0]
    cash = payment_method_id(client, admin, "CASH")
    e = client.post("/api/v1/expenses", headers=mgr, json={"category_id": cat["id"], "amount": 1000, "payment_method_id": cash, "description": "Cleaning supplies"})
    assert e.status_code == 201, e.text

    cur = client.get("/api/v1/cash-sessions/current", headers=mgr).json()
    assert cur["expected_cash"] == 14000
    assert cur["breakdown"]["SALE"] == 5000 and cur["breakdown"]["EXPENSE"] == -1000

    no_reason = client.post(f"/api/v1/cash-sessions/{session['id']}/close", headers=mgr, json={"actual_cash": 13500})
    assert no_reason.status_code == 422 and no_reason.json()["error"]["code"] == "discrepancy_reason_required"
    assert no_reason.json()["error"]["details"]["difference"] == -500
    closed = client.post(f"/api/v1/cash-sessions/{session['id']}/close", headers=mgr, json={"actual_cash": 13500, "reason": "Change given by mistake"})
    assert closed.status_code == 200, closed.text
    c = closed.json()
    assert c["expected_cash"] == 14000 and c["actual_cash"] == 13500 and c["difference"] == -500 and c["status"] == "CLOSED"
    logs = client.get("/api/v1/audit-logs", headers=admin, params={"entity": "cash_session", "entity_id": session["id"]}).json()["items"]
    close_log = next(l for l in logs if l["action"] == "register.close")
    assert close_log["new_value"]["difference"] == "-500.00" and close_log["new_value"]["reason"] == "Change given by mistake"
    notes = client.get("/api/v1/notifications", headers=admin, params={"type": "cash_discrepancy"}).json()
    assert any("-500" in n["message"] for n in notes["items"])
    assert client.post(f"/api/v1/cash-sessions/{session['id']}/close", headers=mgr, json={"actual_cash": 1}).status_code == 409


def test_exact_close_needs_no_reason(client, admin):
    mgr, _ = _new_user(client, admin, "MANAGER")
    reg = client.post("/api/v1/registers", headers=admin, json={"name": f"Counter {uid()}"}).json()
    s = client.post("/api/v1/cash-sessions/open", headers=mgr, json={"register_id": reg["id"], "opening_cash": 500}).json()
    r = client.post(f"/api/v1/cash-sessions/{s['id']}/close", headers=mgr, json={"actual_cash": 500})
    assert r.status_code == 200 and r.json()["difference"] == 0


def test_refund_and_void_flow_through_register(client, admin):
    mgr, _ = _new_user(client, admin, "MANAGER")
    reg = client.post("/api/v1/registers", headers=admin, json={"name": f"Counter {uid()}"}).json()
    client.post("/api/v1/cash-sessions/open", headers=mgr, json={"register_id": reg["id"], "opening_cash": 1000})
    prod = stock_product(client, admin, qty=50, price=100)
    sale = sell(client, mgr, prod["id"], 10, pay=1000).json()
    cash = payment_method_id(client, admin, "CASH")
    client.post("/api/v1/sale-returns", headers=mgr, json={"sale_id": sale["id"], "reason": "faulty", "refund_method_id": cash, "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": 3}]})
    cur = client.get("/api/v1/cash-sessions/current", headers=mgr).json()
    assert cur["expected_cash"] == 1000 + 1000 - 300
    sale2 = sell(client, mgr, prod["id"], 2, pay=200).json()
    client.post(f"/api/v1/sales/{sale2['id']}/void", headers=mgr, json={"reason": "wrong customer"})
    assert client.get("/api/v1/cash-sessions/current", headers=mgr).json()["expected_cash"] == 1700


def test_expenses_crud_void_and_validation(client, admin, cashier):
    cat = client.get("/api/v1/expense-categories", headers=admin).json()[0]
    cash = payment_method_id(client, admin, "CASH")
    body = {"category_id": cat["id"], "amount": 750, "payment_method_id": cash, "description": "Internet bill"}
    r = client.post("/api/v1/expenses", headers=admin, json=body)
    assert r.status_code == 201 and r.json()["expense_number"].startswith("EXP-")
    eid = r.json()["id"]
    assert client.post("/api/v1/expenses", headers=admin, json={**body, "amount": 0}).status_code == 422
    assert client.post("/api/v1/expenses", headers=admin, json={**body, "amount": -5}).status_code == 422
    assert client.post("/api/v1/expenses", headers=admin, json={**body, "category_id": 99999}).status_code == 422
    assert client.post("/api/v1/expenses", headers=cashier, json=body).status_code == 403
    assert client.patch(f"/api/v1/expenses/{eid}", headers=admin, json={"description": "Internet bill (Sept)"}).status_code == 200
    v = client.post(f"/api/v1/expenses/{eid}/void", headers=admin, json={"reason": "entered twice"})
    assert v.status_code == 200 and v.json()["status"] == "VOID"
    assert client.post(f"/api/v1/expenses/{eid}/void", headers=admin, json={"reason": "again again"}).status_code == 409
    listed = client.get("/api/v1/expenses", headers=admin, params={"status": "VOID"}).json()
    assert any(e["id"] == eid for e in listed["items"])  # voided, never deleted


def test_expense_attachment_validation(client, admin):
    cat = client.get("/api/v1/expense-categories", headers=admin).json()[0]
    cash = payment_method_id(client, admin, "CASH")
    eid = client.post("/api/v1/expenses", headers=admin, json={"category_id": cat["id"], "amount": 10, "payment_method_id": cash}).json()["id"]
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    ok = client.post(f"/api/v1/expenses/{eid}/attachment", headers=admin, files={"file": ("receipt.png", png, "image/png")})
    assert ok.status_code == 200 and ok.json()["has_attachment"] is True
    got = client.get(f"/api/v1/expenses/{eid}/attachment", headers=admin)
    assert got.status_code == 200 and got.content.startswith(b"\x89PNG")
    # extension lies: an executable renamed to .png is refused because content is what counts
    evil = client.post(f"/api/v1/expenses/{eid}/attachment", headers=admin, files={"file": ("x.png", b"MZ\x90\x00 not an image", "image/png")})
    assert evil.status_code == 422
    big = client.post(f"/api/v1/expenses/{eid}/attachment", headers=admin, files={"file": ("big.png", png + b"0" * (6 * 1024 * 1024), "image/png")})
    assert big.status_code == 422 and big.json()["error"]["code"] == "file_too_large"
    assert client.get(f"/api/v1/expenses/{eid}/attachment").status_code == 401


def test_customer_ledger_cash_credit_return_scenario(client, admin, manager):
    mgr, _ = _new_user(client, admin, "MANAGER")
    reg = client.post("/api/v1/registers", headers=admin, json={"name": f"Counter {uid()}"}).json()
    client.post("/api/v1/cash-sessions/open", headers=mgr, json={"register_id": reg["id"], "opening_cash": 0})
    prod = stock_product(client, admin, qty=100, price=500)
    cust = make_customer(client, admin, credit_limit=100000)
    cash = payment_method_id(client, admin, "CASH")
    sell(client, mgr, prod["id"], 2, customer_id=cust["id"])  # 1000 cash sale
    cs = client.post("/api/v1/sales", headers=mgr, json={"items": [{"product_id": prod["id"], "quantity": 10}], "customer_id": cust["id"], "payments": [{"payment_method_id": cash, "amount": 3000}]}).json()
    assert cs["due_amount"] == 2000
    client.post(f"/api/v1/customers/{cust['id']}/payments", headers=admin, json={"amount": 500, "payment_method_id": cash})
    client.post("/api/v1/sale-returns", headers=mgr, json={"sale_id": cs["id"], "reason": "too many", "refund_method_id": cash, "items": [{"sale_item_id": cs["items"][0]["id"], "quantity": 2}]})
    prof = client.get(f"/api/v1/customers/{cust['id']}", headers=admin).json()
    assert prof["balance"] == 2000 - 500 - 1000
    assert prof["total_purchases"] == 6000 and prof["total_returns"] == 1000 and prof["total_paid"] == 500
    rows = client.get(f"/api/v1/customers/{cust['id']}/ledger", headers=admin).json()["items"]
    assert rows[0]["balance_after"] == 500
    assert len(rows) == 6
