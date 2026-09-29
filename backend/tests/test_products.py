from decimal import Decimal

from tests.helpers import make_category, make_product, stock_of, uid, unit_id


def test_create_and_fetch_product(client, admin):
    cat = make_category(client, admin)
    p = make_product(client, admin, category_id=cat["id"], name_bn="পণ্য")
    got = client.get(f"/api/v1/products/{p['id']}", headers=admin).json()
    assert got["sku"] == p["sku"] and got["barcode"] == p["barcode"]
    assert got["category"]["id"] == cat["id"]
    assert got["current_stock"] == 0
    assert got["unit"]["short_name"] == "pc"


def test_duplicate_sku_and_barcode_rejected(client, admin):
    p = make_product(client, admin)
    r = client.post("/api/v1/products", headers=admin, json={"sku": p["sku"].lower(), "name": "Dup", "unit_id": unit_id(client, admin), "selling_price": 10})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_sku"
    r = client.post("/api/v1/products", headers=admin, json={"sku": f"NEW-{uid()}", "name": "Dup", "unit_id": unit_id(client, admin), "selling_price": 10, "barcode": p["barcode"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_barcode"


def test_invalid_product_payloads(client, admin):
    base = {"sku": f"BAD-{uid()}", "name": "Bad", "unit_id": unit_id(client, admin)}
    assert client.post("/api/v1/products", headers=admin, json={**base, "selling_price": -1}).status_code == 422
    assert client.post("/api/v1/products", headers=admin, json={**base, "selling_price": 5, "purchase_price": -3}).status_code == 422
    assert client.post("/api/v1/products", headers=admin, json={**base, "selling_price": 5, "min_stock": 10, "max_stock": 5}).status_code == 422
    assert client.post("/api/v1/products", headers=admin, json={**base, "selling_price": 5, "unit_id": 99999}).status_code == 422
    assert client.post("/api/v1/products", headers=admin, json={"name": "no sku"}).status_code == 422


def test_search_filter_and_pagination(client, admin):
    cat = make_category(client, admin)
    for _ in range(3):
        make_product(client, admin, category_id=cat["id"])
    named = make_product(client, admin, name="Zebra Special Biscuit", category_id=cat["id"])
    r = client.get("/api/v1/products", headers=admin, params={"search": "zebra special"}).json()
    assert r["total"] == 1 and r["items"][0]["id"] == named["id"]
    by_barcode = client.get("/api/v1/products", headers=admin, params={"search": named["barcode"]}).json()
    assert by_barcode["total"] == 1
    page = client.get("/api/v1/products", headers=admin, params={"category_id": cat["id"], "page_size": 2}).json()
    assert page["total"] == 4 and len(page["items"]) == 2 and page["pages"] == 2


def test_purchase_price_hidden_and_protected(client, admin, tokens):
    p = make_product(client, admin, purchase_price=120)
    assert client.get(f"/api/v1/products/{p['id']}", headers=admin).json()["purchase_price"] == 120
    inv = tokens["INVENTORY_MANAGER"]  # can update products but has no product.cost
    assert client.get(f"/api/v1/products/{p['id']}", headers=inv).json()["purchase_price"] is None
    r = client.patch(f"/api/v1/products/{p['id']}", headers=inv, json={"purchase_price": 1})
    assert r.status_code == 403
    assert client.patch(f"/api/v1/products/{p['id']}", headers=inv, json={"name": "Renamed"}).status_code == 200
    cashier = tokens["CASHIER"]
    assert client.patch(f"/api/v1/products/{p['id']}", headers=cashier, json={"name": "x"}).status_code == 403
    assert client.delete(f"/api/v1/products/{p['id']}", headers=cashier).status_code == 403


def test_price_change_is_audited(client, admin):
    p = make_product(client, admin)
    assert client.patch(f"/api/v1/products/{p['id']}", headers=admin, json={"selling_price": 175}).status_code == 200
    logs = client.get("/api/v1/audit-logs", headers=admin, params={"entity": "product", "entity_id": p["id"], "action": "product.price_change"}).json()
    assert logs["total"] == 1
    assert logs["items"][0]["old_value"]["selling_price"] == "150.00"
    assert logs["items"][0]["new_value"]["selling_price"] == "175.00"
    assert logs["items"][0]["user_email"] == "admin@example.com"


def test_delete_blocked_while_stock_exists_then_soft_deleted(client, admin):
    p = make_product(client, admin)
    r = client.post("/api/v1/inventory/adjustments", headers=admin, json={"product_id": p["id"], "adjustment_type": "IN", "quantity": 5, "reason": "opening stock"})
    assert r.status_code == 201, r.text
    d = client.delete(f"/api/v1/products/{p['id']}", headers=admin)
    assert d.status_code == 409 and d.json()["error"]["code"] == "product_has_stock"
    client.post("/api/v1/inventory/adjustments", headers=admin, json={"product_id": p["id"], "adjustment_type": "OUT", "quantity": 5, "reason": "clear"})
    assert client.delete(f"/api/v1/products/{p['id']}", headers=admin).status_code == 200
    assert client.get(f"/api/v1/products/{p['id']}", headers=admin).status_code == 404
    # SKU stays reserved after soft-delete so history never becomes ambiguous
    r = client.post("/api/v1/products", headers=admin, json={"sku": p["sku"], "name": "again", "unit_id": unit_id(client, admin), "selling_price": 1})
    assert r.status_code == 409


def test_stock_adjustments_need_reason_and_never_go_negative(client, admin):
    p = make_product(client, admin)
    pid = p["id"]
    bad = client.post("/api/v1/inventory/adjustments", headers=admin, json={"product_id": pid, "adjustment_type": "IN", "quantity": 5, "reason": " "})
    assert bad.status_code == 422
    client.post("/api/v1/inventory/adjustments", headers=admin, json={"product_id": pid, "adjustment_type": "IN", "quantity": 10, "reason": "count"})
    over = client.post("/api/v1/inventory/adjustments", headers=admin, json={"product_id": pid, "adjustment_type": "OUT", "quantity": 11, "reason": "oops"})
    assert over.status_code == 409 and over.json()["error"]["code"] == "insufficient_stock"
    assert stock_of(client, admin, pid) == Decimal("10")
    client.post("/api/v1/inventory/adjustments", headers=admin, json={"product_id": pid, "adjustment_type": "DAMAGE", "quantity": 3, "reason": "dropped"})
    assert stock_of(client, admin, pid) == Decimal("7")
    moves = client.get("/api/v1/inventory/movements", headers=admin, params={"product_id": pid}).json()["items"]
    assert [m["txn_type"] for m in moves] == ["DAMAGE", "ADJUSTMENT_IN"]
    assert moves[0]["quantity"] == -3 and moves[0]["balance_after"] == 7
    stock = client.get("/api/v1/inventory/stock", headers=admin, params={"search": p["sku"]}).json()["items"][0]
    assert stock["damaged_stock"] == 3 and stock["current_stock"] == 7


def test_expiry_tracking_requires_date_and_fefo(client, admin):
    from datetime import date, timedelta

    p = make_product(client, admin, track_expiry=True)
    no_date = client.post("/api/v1/inventory/adjustments", headers=admin, json={"product_id": p["id"], "adjustment_type": "IN", "quantity": 5, "reason": "no date"})
    assert no_date.status_code == 422 and no_date.json()["error"]["code"] == "expiry_required"
    late = (date.today() + timedelta(days=90)).isoformat()
    soon = (date.today() + timedelta(days=10)).isoformat()
    client.post("/api/v1/inventory/adjustments", headers=admin, json={"product_id": p["id"], "adjustment_type": "IN", "quantity": 5, "reason": "late", "expiry_date": late, "batch_number": "LATE"})
    client.post("/api/v1/inventory/adjustments", headers=admin, json={"product_id": p["id"], "adjustment_type": "IN", "quantity": 5, "reason": "soon", "expiry_date": soon, "batch_number": "SOON"})
    client.post("/api/v1/inventory/adjustments", headers=admin, json={"product_id": p["id"], "adjustment_type": "OUT", "quantity": 6, "reason": "fefo test"})
    batches = {b["batch_number"]: b for b in client.get("/api/v1/inventory/batches", headers=admin, params={"product_id": p["id"], "include_empty": True}).json()["items"]}
    assert batches["SOON"]["quantity_remaining"] == 0  # earliest expiry consumed first
    assert batches["LATE"]["quantity_remaining"] == 4
    exp = client.get("/api/v1/inventory/expiring", headers=admin, params={"days": 30}).json()
    assert any(b["product_id"] == p["id"] for b in exp["items"]) is False  # SOON is empty now
