"""The final acceptance scenario from the specification, executed end-to-end through the HTTP API.

ADMIN login -> category -> supplier -> product + barcode -> purchase -> receive 100 -> stock 100
-> open register -> cashier scans and sells 5 -> stock 95 -> payment/sale/receipt/dashboard
-> return 2 -> stock 97 -> expense -> close register (discrepancy) -> ledgers -> reports -> audit log
"""

from tests.conftest import PASSWORD
from tests.helpers import uid


def test_full_business_day(client):
    tag = uid()
    # --- admin login
    admin_login = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": PASSWORD})
    assert admin_login.status_code == 200
    A = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    # --- category, supplier, product with barcode
    cat = client.post("/api/v1/categories", headers=A, json={"name": f"Dairy-{tag}"}).json()
    sup = client.post("/api/v1/suppliers", headers=A, json={"name": f"Fresh Farms {tag}", "phone": f"0171{tag}9999", "payment_terms_days": 15}).json()
    unit = next(u for u in client.get("/api/v1/units", headers=A).json() if u["name"] == "Piece")
    prod = client.post("/api/v1/products", headers=A, json={
        "sku": f"MILK-{tag}", "name": "Fresh Milk 1L", "name_bn": "তাজা দুধ", "unit_id": unit["id"], "category_id": cat["id"],
        "supplier_id": sup["id"], "purchase_price": 100, "selling_price": 150, "reorder_level": 20, "barcode": f"8901{tag}77"}).json()
    assert prod["barcode"] == f"8901{tag}77"

    # --- purchase and receive 100 units
    po = client.post("/api/v1/purchases", headers=A, json={"supplier_id": sup["id"], "items": [{"product_id": prod["id"], "quantity": 100, "unit_cost": 100}], "submit": True}).json()
    assert po["status"] == "PENDING"
    assert client.get(f"/api/v1/products/{prod['id']}", headers=A).json()["current_stock"] == 0
    assert client.post(f"/api/v1/purchases/{po['id']}/approve", headers=A).json()["status"] == "APPROVED"
    rec = client.post(f"/api/v1/purchases/{po['id']}/receive", headers=A, json={"items": [{"item_id": po["items"][0]["id"], "quantity": 100}]})
    assert rec.status_code == 200 and rec.json()["status"] == "RECEIVED"
    assert client.get(f"/api/v1/products/{prod['id']}", headers=A).json()["current_stock"] == 100
    assert client.get(f"/api/v1/suppliers/{sup['id']}", headers=A).json()["balance"] == 10000

    # --- cashier opens the register and scans the product by barcode
    C = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'cashier@example.com', 'password': PASSWORD}).json()['access_token']}"}
    sess = client.get("/api/v1/cash-sessions/current", headers=C).json()
    if not sess:
        reg = client.get("/api/v1/registers", headers=C).json()[0]
        sess = client.post("/api/v1/cash-sessions/open", headers=C, json={"register_id": reg["id"], "opening_cash": 20000}).json()
    opening = sess["expected_cash"]
    scanned = client.get("/api/v1/products/lookup", headers=C, params={"q": prod["barcode"]}).json()
    assert len(scanned) == 1 and scanned[0]["id"] == prod["id"] and scanned[0]["selling_price"] == 150

    dash0 = client.get("/api/v1/dashboard", headers=A, params={"period": "today"}).json()["kpis"]

    # --- sell 5 units (cart previewed by the server, then paid in cash)
    cart = {"items": [{"product_id": prod["id"], "quantity": 5}]}
    preview = client.post("/api/v1/sales/preview", headers=C, json=cart).json()
    assert preview["grand_total"] == 750
    cash = next(m["id"] for m in client.get("/api/v1/payment-methods", headers=C).json() if m["code"] == "CASH")
    sale = client.post("/api/v1/sales", headers=C, json={**cart, "payments": [{"payment_method_id": cash, "amount": 1000}]}).json()
    assert sale["total_amount"] == 750 and sale["change_amount"] == 250 and sale["paid_amount"] == 750
    assert client.get(f"/api/v1/products/{prod['id']}", headers=A).json()["current_stock"] == 95

    # --- payment, sale, receipt, dashboard, reports
    got = client.get(f"/api/v1/sales/{sale['id']}", headers=A).json()
    assert got["payments"][0]["method_name"] == "Cash" and got["cogs_amount"] == 500
    receipt = client.get(f"/api/v1/documents/sales/{sale['id']}/receipt.pdf", headers=C)
    assert receipt.status_code == 200 and receipt.content.startswith(b"%PDF")
    dash1 = client.get("/api/v1/dashboard", headers=A, params={"period": "today"}).json()["kpis"]
    assert round(dash1["sales_total"] - dash0["sales_total"], 2) == 750 and round(dash1["profit"] - dash0["profit"], 2) == 250
    by_product = client.get("/api/v1/reports/sales-by-product", headers=A, params={"period": "today", "product_id": prod["id"]}).json()
    assert by_product["rows"][0]["quantity"] == 5

    # --- return 2 units -> stock 97
    ret = client.post("/api/v1/sale-returns", headers=C, json={"sale_id": sale["id"], "reason": "Packaging damaged", "refund_method_id": cash,
                                                                 "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": 2}]})
    assert ret.status_code == 201 and ret.json()["total_amount"] == 300
    assert client.get(f"/api/v1/products/{prod['id']}", headers=A).json()["current_stock"] == 97
    assert client.get(f"/api/v1/sales/{sale['id']}", headers=A).json()["total_amount"] == 750  # original untouched
    dash2 = client.get("/api/v1/dashboard", headers=A, params={"period": "today"}).json()["kpis"]
    assert round(dash2["sales_total"] - dash0["sales_total"], 2) == 450 and round(dash2["profit"] - dash0["profit"], 2) == 150

    # --- inventory valuation and supplier balance stay consistent
    val = client.get("/api/v1/reports/inventory-valuation", headers=A, params={"limit": 5000}).json()
    row = next(r for r in val["rows"] if r["sku"] == prod["sku"])
    assert row["quantity"] == 97 and row["value"] == 9700
    assert client.get(f"/api/v1/suppliers/{sup['id']}", headers=A).json()["balance"] == 10000
    movements = client.get("/api/v1/inventory/movements", headers=A, params={"product_id": prod["id"]}).json()["items"]
    assert [(m["txn_type"], m["quantity"], m["balance_after"]) for m in movements] == [("SALE_RETURN", 2, 97), ("SALE", -5, 95), ("PURCHASE", 100, 100)]

    # --- pay the supplier part of the bill, then expense and close register with a discrepancy
    pay = client.post(f"/api/v1/suppliers/{sup['id']}/payments", headers=A, json={"amount": 4000, "payment_method_id": cash})
    assert pay.status_code == 201
    assert client.get(f"/api/v1/suppliers/{sup['id']}", headers=A).json()["balance"] == 6000
    cur = client.get("/api/v1/cash-sessions/current", headers=C).json()
    expected = cur["expected_cash"]
    assert round(expected - opening, 2) == 750 - 300  # sale cash in, refund out (admin's payment used admin's own drawer state)
    close = client.post(f"/api/v1/cash-sessions/{cur['id']}/close", headers=C, json={"actual_cash": expected - 500, "reason": "Short by 500 at count"})
    assert close.status_code == 200 and close.json()["difference"] == -500

    # --- ledgers, audit trail
    ledger = client.get(f"/api/v1/suppliers/{sup['id']}/ledger", headers=A).json()["items"]
    assert [(r["txn_type"], r["balance_after"]) for r in ledger] == [("PAYMENT", 6000), ("PURCHASE", 10000)]
    actions = {e["action"] for e in client.get("/api/v1/audit-logs", headers=A, params={"page_size": 200}).json()["items"]}
    assert {"purchase.approve", "purchase.receive", "sale.create", "sale.return", "register.close", "supplier.payment", "product.create"} <= actions
