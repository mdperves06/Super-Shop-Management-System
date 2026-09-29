import itertools
from decimal import Decimal

_counter = itertools.count(1)


def uid() -> str:
    return f"{next(_counter):05d}"


def unit_id(client, headers, name="Piece") -> int:
    return next(u["id"] for u in client.get("/api/v1/units", headers=headers).json() if u["name"] == name)


def make_category(client, headers, name=None) -> dict:
    r = client.post("/api/v1/categories", headers=headers, json={"name": name or f"Cat-{uid()}"})
    assert r.status_code == 201, r.text
    return r.json()


def make_product(client, headers, **over) -> dict:
    n = uid()
    payload = {
        "sku": f"SKU-{n}", "name": f"Product {n}", "unit_id": unit_id(client, headers),
        "purchase_price": 100, "selling_price": 150, "reorder_level": 5, "barcode": f"890{n}0000",
    }
    payload.update(over)
    r = client.post("/api/v1/products", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def make_supplier(client, headers, **over) -> dict:
    n = uid()
    payload = {"name": f"Supplier {n}", "phone": f"0171{n}0000"}
    payload.update(over)
    r = client.post("/api/v1/suppliers", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def make_customer(client, headers, **over) -> dict:
    n = uid()
    payload = {"name": f"Customer {n}", "phone": f"0181{n}0000"}
    payload.update(over)
    r = client.post("/api/v1/customers", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def stock_of(client, headers, product_id) -> Decimal:
    return Decimal(str(client.get(f"/api/v1/products/{product_id}", headers=headers).json()["current_stock"]))


def payment_method_id(client, headers, code="CASH") -> int:
    return next(m["id"] for m in client.get("/api/v1/payment-methods", headers=headers).json() if m["code"] == code)


def stock_product(client, headers, qty=100, cost=100, price=150, **product_over) -> dict:
    """Create a product and receive `qty` units of it through a real purchase order."""
    product = make_product(client, headers, purchase_price=0, selling_price=price, **product_over)
    supplier = make_supplier(client, headers)
    po = client.post("/api/v1/purchases", headers=headers, json={
        "supplier_id": supplier["id"], "items": [{"product_id": product["id"], "quantity": qty, "unit_cost": cost}]}).json()
    assert client.post(f"/api/v1/purchases/{po['id']}/approve", headers=headers).status_code == 200
    item = po["items"][0]
    body = {"items": [{"item_id": item["id"], "quantity": qty}]}
    if product_over.get("track_expiry"):
        from datetime import date, timedelta
        body["items"][0]["expiry_date"] = (date.today() + timedelta(days=180)).isoformat()
    r = client.post(f"/api/v1/purchases/{po['id']}/receive", headers=headers, json=body)
    assert r.status_code == 200, r.text
    product["supplier_id_used"] = supplier["id"]
    product["po"] = po
    return product


def ensure_register_open(client, headers, opening=5000, register="Main Counter"):
    cur = client.get("/api/v1/cash-sessions/current", headers=headers).json()
    if cur:
        return cur
    regs = client.get("/api/v1/registers", headers=headers).json()
    reg = next((r for r in regs if r["name"] == register), None)
    assert reg, f"register {register} missing"
    r = client.post("/api/v1/cash-sessions/open", headers=headers, json={"register_id": reg["id"], "opening_cash": opening})
    assert r.status_code == 201, r.text
    return r.json()


def sell(client, headers, product_id, qty, *, pay=None, method="CASH", **extra):
    """POST /sales; pay=None pays the exact server-computed total in cash."""
    items = extra.pop("items", None) or [{"product_id": product_id, "quantity": qty}]
    body = {"items": items, **extra}
    if pay is None:
        prev = client.post("/api/v1/sales/preview", headers=headers, json={k: v for k, v in body.items() if k in ("items", "customer_id", "invoice_discount_type", "invoice_discount_value")}).json()
        pay = prev["grand_total"]
    if "payments" not in body and pay:
        body["payments"] = [{"payment_method_id": payment_method_id(client, headers, method), "amount": pay}]
    return client.post("/api/v1/sales", headers=headers, json=body)
