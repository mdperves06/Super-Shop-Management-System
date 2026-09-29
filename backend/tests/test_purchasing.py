from decimal import Decimal

from tests.helpers import make_product, make_supplier, payment_method_id, stock_of


def _po(client, headers, supplier, items, **over):
    body = {"supplier_id": supplier["id"], "items": items, **over}
    r = client.post("/api/v1/purchases", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _balance(client, headers, supplier_id) -> Decimal:
    return Decimal(str(client.get(f"/api/v1/suppliers/{supplier_id}", headers=headers).json()["balance"]))


def test_purchase_order_does_not_change_stock_until_received(client, admin):
    sup = make_supplier(client, admin)
    prod = make_product(client, admin)
    po = _po(client, admin, sup, [{"product_id": prod["id"], "quantity": 100, "unit_cost": 100}])
    assert po["status"] == "DRAFT" and po["total_amount"] == 10000
    assert stock_of(client, admin, prod["id"]) == 0 and _balance(client, admin, sup["id"]) == 0
    # cannot receive a draft
    item = po["items"][0]
    r = client.post(f"/api/v1/purchases/{po['id']}/receive", headers=admin, json={"items": [{"item_id": item["id"], "quantity": 10}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "purchase_not_receivable"
    client.post(f"/api/v1/purchases/{po['id']}/submit", headers=admin)
    assert client.post(f"/api/v1/purchases/{po['id']}/approve", headers=admin).json()["status"] == "APPROVED"
    assert stock_of(client, admin, prod["id"]) == 0  # approval alone does nothing either


def test_receive_partial_then_rest_updates_stock_and_payable(client, admin):
    sup = make_supplier(client, admin)
    prod = make_product(client, admin, purchase_price=0)
    po = _po(client, admin, sup, [{"product_id": prod["id"], "quantity": 100, "unit_cost": 100, "discount_amount": 500, "tax_rate": 10}])
    # gross 10000 - 500 discount = 9500 ; +10% tax = 10450
    assert po["total_amount"] == 10450
    client.post(f"/api/v1/purchases/{po['id']}/approve", headers=admin)
    item = po["items"][0]
    r = client.post(f"/api/v1/purchases/{po['id']}/receive", headers=admin, json={"items": [{"item_id": item["id"], "quantity": 40, "batch_number": "B-A"}]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PARTIALLY_RECEIVED"
    assert stock_of(client, admin, prod["id"]) == 40
    assert _balance(client, admin, sup["id"]) == Decimal("4180.00")  # 40/100 of 10450
    over = client.post(f"/api/v1/purchases/{po['id']}/receive", headers=admin, json={"items": [{"item_id": item["id"], "quantity": 61}]})
    assert over.status_code == 422 and over.json()["error"]["code"] == "over_receipt"
    r = client.post(f"/api/v1/purchases/{po['id']}/receive", headers=admin, json={"items": [{"item_id": item["id"], "quantity": 60, "batch_number": "B-B"}]})
    assert r.json()["status"] == "RECEIVED"
    assert stock_of(client, admin, prod["id"]) == 100
    assert _balance(client, admin, sup["id"]) == Decimal("10450.00")  # exact, no rounding drift
    # batch cost excludes VAT and includes the discount: (10000-500)/100 = 95
    got = client.get(f"/api/v1/products/{prod['id']}", headers=admin).json()
    assert got["purchase_price"] == 95
    # stock ledger
    moves = client.get("/api/v1/inventory/movements", headers=admin, params={"product_id": prod["id"]}).json()["items"]
    assert [(m["txn_type"], m["quantity"], m["balance_after"]) for m in moves] == [("PURCHASE", 60, 100), ("PURCHASE", 40, 40)]
    # cancelled after receipt is refused
    assert client.post(f"/api/v1/purchases/{po['id']}/cancel", headers=admin, json={"reason": "too late"}).status_code == 409


def test_supplier_payment_and_ledger(client, admin):
    sup = make_supplier(client, admin, opening_balance=1000)
    assert _balance(client, admin, sup["id"]) == 1000
    prod = make_product(client, admin)
    po = _po(client, admin, sup, [{"product_id": prod["id"], "quantity": 10, "unit_cost": 50}])
    client.post(f"/api/v1/purchases/{po['id']}/approve", headers=admin)
    client.post(f"/api/v1/purchases/{po['id']}/receive", headers=admin, json={"items": [{"item_id": po["items"][0]["id"], "quantity": 10}]})
    assert _balance(client, admin, sup["id"]) == 1500
    cash = payment_method_id(client, admin, "CASH")
    r = client.post(f"/api/v1/suppliers/{sup['id']}/payments", headers=admin, json={"amount": 600, "payment_method_id": cash, "purchase_id": po["id"]})
    assert r.status_code == 201, r.text
    assert _balance(client, admin, sup["id"]) == 900
    over = client.post(f"/api/v1/suppliers/{sup['id']}/payments", headers=admin, json={"amount": 5000, "payment_method_id": cash})
    assert over.status_code == 422 and over.json()["error"]["code"] == "overpayment"
    bkash = payment_method_id(client, admin, "BKASH")
    noref = client.post(f"/api/v1/suppliers/{sup['id']}/payments", headers=admin, json={"amount": 10, "payment_method_id": bkash})
    assert noref.status_code == 422 and noref.json()["error"]["code"] == "reference_required"
    ledger = client.get(f"/api/v1/suppliers/{sup['id']}/ledger", headers=admin).json()["items"]
    assert [(r["txn_type"], r["amount"], r["balance_after"]) for r in ledger] == [("PAYMENT", -600, 900), ("PURCHASE", 500, 1500), ("OPENING", 1000, 1000)]
    prof = client.get(f"/api/v1/suppliers/{sup['id']}", headers=admin).json()
    assert prof["total_purchases"] == 500 and prof["total_paid"] == 600 and prof["balance"] == 900
    assert client.get(f"/api/v1/purchases/{po['id']}", headers=admin).json()["paid_amount"] == 600


def test_purchase_return_reduces_stock_and_payable(client, admin):
    sup = make_supplier(client, admin)
    prod = make_product(client, admin)
    po = _po(client, admin, sup, [{"product_id": prod["id"], "quantity": 20, "unit_cost": 100}])
    client.post(f"/api/v1/purchases/{po['id']}/approve", headers=admin)
    client.post(f"/api/v1/purchases/{po['id']}/receive", headers=admin, json={"items": [{"item_id": po["items"][0]["id"], "quantity": 20, "batch_number": "RET-B"}]})
    batch = client.get("/api/v1/inventory/batches", headers=admin, params={"product_id": prod["id"]}).json()["items"][0]
    r = client.post("/api/v1/purchase-returns", headers=admin, json={
        "supplier_id": sup["id"], "purchase_id": po["id"], "reason": "damaged on arrival",
        "items": [{"product_id": prod["id"], "batch_id": batch["id"], "quantity": 5}]})
    assert r.status_code == 201, r.text
    assert r.json()["total_amount"] == 500 and r.json()["return_number"].startswith("PRET-")
    assert stock_of(client, admin, prod["id"]) == 15
    assert _balance(client, admin, sup["id"]) == 1500
    too_many = client.post("/api/v1/purchase-returns", headers=admin, json={
        "supplier_id": sup["id"], "purchase_id": po["id"], "reason": "again",
        "items": [{"product_id": prod["id"], "batch_id": batch["id"], "quantity": 16}]})
    assert too_many.status_code in (409, 422)
    assert stock_of(client, admin, prod["id"]) == 15 and _balance(client, admin, sup["id"]) == 1500


def test_draft_editing_and_permissions(client, admin, tokens):
    sup = make_supplier(client, admin)
    prod = make_product(client, admin)
    po = _po(client, admin, sup, [{"product_id": prod["id"], "quantity": 5, "unit_cost": 10}])
    r = client.put(f"/api/v1/purchases/{po['id']}", headers=admin, json={"items": [{"product_id": prod["id"], "quantity": 7, "unit_cost": 20}]})
    assert r.status_code == 200 and r.json()["total_amount"] == 140
    # cashier has no purchasing rights at all; inventory manager can receive but not approve/pay
    assert client.post("/api/v1/purchases", headers=tokens["CASHIER"], json={"supplier_id": sup["id"], "items": [{"product_id": prod["id"], "quantity": 1, "unit_cost": 1}]}).status_code == 403
    assert client.post(f"/api/v1/purchases/{po['id']}/approve", headers=tokens["INVENTORY_MANAGER"]).status_code == 403
    client.post(f"/api/v1/purchases/{po['id']}/approve", headers=admin)
    assert client.put(f"/api/v1/purchases/{po['id']}", headers=admin, json={"notes": "late edit"}).status_code == 409
    assert client.post(f"/api/v1/suppliers/{sup['id']}/payments", headers=tokens["INVENTORY_MANAGER"], json={"amount": 1, "payment_method_id": 1}).status_code == 403
    assert client.post(f"/api/v1/suppliers/{sup['id']}/adjustments", headers=tokens["CASHIER"], json={"amount": 100, "reason": "fudge"}).status_code == 403


def test_duplicate_supplier_phone_and_invalid_items(client, admin):
    sup = make_supplier(client, admin)
    dup = client.post("/api/v1/suppliers", headers=admin, json={"name": "Other", "phone": sup["phone"]})
    assert dup.status_code == 409
    prod = make_product(client, admin)
    bad = client.post("/api/v1/purchases", headers=admin, json={"supplier_id": sup["id"], "items": [{"product_id": prod["id"], "quantity": 0, "unit_cost": 5}]})
    assert bad.status_code == 422
    bad = client.post("/api/v1/purchases", headers=admin, json={"supplier_id": sup["id"], "items": [{"product_id": prod["id"], "quantity": 1, "unit_cost": -5}]})
    assert bad.status_code == 422
    bad = client.post("/api/v1/purchases", headers=admin, json={"supplier_id": 99999, "items": [{"product_id": prod["id"], "quantity": 1, "unit_cost": 5}]})
    assert bad.status_code == 422
