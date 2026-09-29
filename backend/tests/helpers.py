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
