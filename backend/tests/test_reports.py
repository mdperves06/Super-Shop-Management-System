import io
from datetime import date

import pytest

from tests.helpers import ensure_register_open, make_product, payment_method_id, sell, stock_product


@pytest.fixture(scope="module")
def desk(client, cashier):
    return ensure_register_open(client, cashier, 5000)


def _dash(client, headers, **params):
    r = client.get("/api/v1/dashboard", headers=headers, params={"period": "today", **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_dashboard_kpis_move_by_exactly_the_sale_and_return(client, admin, cashier, desk):
    prod = stock_product(client, admin, qty=100, cost=100, price=150)
    before = _dash(client, admin)["kpis"]
    sale = sell(client, cashier, prod["id"], 5).json()
    mid = _dash(client, admin)["kpis"]
    assert round(mid["sales_total"] - before["sales_total"], 2) == 750
    assert round(mid["profit"] - before["profit"], 2) == 250  # 750 revenue - 500 COGS
    assert mid["invoices"] - before["invoices"] == 1
    cash = payment_method_id(client, admin, "CASH")
    client.post("/api/v1/sale-returns", headers=cashier, json={"sale_id": sale["id"], "reason": "return two", "refund_method_id": cash, "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": 2}]})
    after = _dash(client, admin)["kpis"]
    assert round(after["sales_total"] - before["sales_total"], 2) == 450
    assert round(after["profit"] - before["profit"], 2) == 150  # 3 units net: 450 revenue - 300 COGS
    assert round(after["stock_value"] - before["stock_value"], 2) == -300  # 3 net units left the shelf at cost 100
    # inventory valuation: 97 units left at cost 100
    val = client.get("/api/v1/reports/inventory-valuation", headers=admin, params={"limit": 5000}).json()
    row = next(r for r in val["rows"] if r["sku"] == prod["sku"])
    assert row["quantity"] == 97 and row["value"] == 9700


def test_dashboard_is_permission_aware(client, admin, cashier, tokens, desk):
    d = _dash(client, cashier)
    assert d["kpis"]["profit"] is None and d["kpis"]["purchases"] is None and d["kpis"]["stock_value"] is None
    assert d["kpis"]["supplier_payables"] is None
    assert all("profit" not in row for row in d["series"])
    full = _dash(client, tokens["ACCOUNTANT"])
    assert full["kpis"]["profit"] is not None and full["kpis"]["supplier_payables"] is not None
    assert client.get("/api/v1/dashboard", headers=tokens["STAFF"]).status_code == 200
    # cashier only sees their own sales
    assert d["kpis"]["invoices"] <= _dash(client, admin)["kpis"]["invoices"]


def test_dashboard_periods_and_validation(client, admin):
    for p in ("today", "yesterday", "last_7_days", "this_month", "last_month", "this_year"):
        d = _dash(client, admin, period=p)
        assert d["period"]["start"] <= d["period"]["end"]
    d = _dash(client, admin, period="custom", start="2020-01-01", end="2020-01-31")
    assert d["kpis"]["sales_total"] == 0 and len(d["series"]) == 31
    assert client.get("/api/v1/dashboard", headers=admin, params={"period": "custom"}).status_code == 422
    assert client.get("/api/v1/dashboard", headers=admin, params={"period": "custom", "start": "2020-02-01", "end": "2020-01-01"}).status_code == 422
    assert client.get("/api/v1/dashboard", headers=admin, params={"period": "nonsense"}).status_code == 422
    yr = _dash(client, admin, period="this_year")
    assert yr["period"]["granularity"] == "month"
    assert _dash(client, admin)["period"]["granularity"] == "hour"


def test_dashboard_top_products_and_categories(client, admin, cashier, desk):
    prod = stock_product(client, admin, qty=100, price=100)
    sell(client, cashier, prod["id"], 30)
    d = _dash(client, admin, top_n=5)
    assert len(d["top_products"]) <= 5
    assert d["top_products"][0]["quantity"] >= 30
    assert d["category_sales"] and d["inventory_status"]
    assert sum(x["count"] for x in d["inventory_status"]) > 0
    assert {"type", "number", "amount"} <= set(d["recent"][0])


def test_sales_and_profit_reports(client, admin, cashier, desk):
    prod = stock_product(client, admin, qty=40, cost=60, price=100)
    sell(client, cashier, prod["id"], 4)
    rep = client.get("/api/v1/reports/sales-by-product", headers=admin, params={"period": "today", "product_id": prod["id"]}).json()
    assert len(rep["rows"]) == 1 and rep["rows"][0]["quantity"] == 4 and rep["rows"][0]["sales"] == 400 and rep["rows"][0]["profit"] == 160
    summ = client.get("/api/v1/reports/sales-summary", headers=admin, params={"period": "today", "group_by": "day"}).json()
    assert summ["rows"][0]["period"] == date.today().isoformat() or summ["rows"][0]["period"] > "2020"
    assert summ["summary"]["net_sales"] > 0 and "profit" in summ["summary"]
    for name in ("sales-by-category", "sales-by-employee", "sales-by-payment-method", "sales-by-customer", "profit", "expenses", "cash-flow",
                 "payables", "receivables", "cash-registers", "inventory-current", "low-stock", "out-of-stock", "expiring", "expired",
                 "stock-movement", "purchases-by-supplier", "purchases-by-date", "purchase-returns"):
        r = client.get(f"/api/v1/reports/{name}", headers=admin, params={"period": "this_year"})
        assert r.status_code == 200, (name, r.text)
        assert r.json()["columns"], name
    for gran in ("day", "week", "month", "year"):
        assert client.get("/api/v1/reports/profit", headers=admin, params={"period": "this_year", "group_by": gran}).status_code == 200
    assert client.get("/api/v1/reports/nope", headers=admin).status_code == 404


def test_profit_report_consistent_with_dashboard(client, admin, cashier, desk):
    d = _dash(client, admin, period="this_year")["kpis"]
    p = client.get("/api/v1/reports/profit", headers=admin, params={"period": "this_year", "group_by": "month"}).json()
    assert round(p["summary"]["gross_profit"], 2) == round(d["profit"], 2)
    assert round(sum(r["profit"] for r in p["rows"]), 2) == round(d["profit"], 2)
    assert round(p["summary"]["net_profit"], 2) == round(d["net_profit"], 2)


def test_report_permissions(client, cashier, tokens):
    assert client.get("/api/v1/reports/sales-summary", headers=cashier).status_code == 403
    assert client.get("/api/v1/reports/profit", headers=tokens["INVENTORY_MANAGER"]).status_code == 403
    assert client.get("/api/v1/reports/low-stock", headers=tokens["INVENTORY_MANAGER"]).status_code == 200
    assert client.get("/api/v1/reports/low-stock", headers=tokens["INVENTORY_MANAGER"], params={"format": "csv"}).status_code == 403  # no report.export
    assert client.get("/api/v1/reports", headers=cashier).json() == []
    names = {r["name"] for r in client.get("/api/v1/reports", headers=tokens["ACCOUNTANT"]).json()}
    assert {"profit", "cash-flow", "sales-summary"} <= names


def test_report_exports(client, admin, cashier, desk):
    prod = stock_product(client, admin, qty=10, price=100, name="=cmd|' /C calc'!A0 Export Test")
    sell(client, cashier, prod["id"], 1)
    csv_r = client.get("/api/v1/reports/sales-by-product", headers=admin, params={"period": "today", "format": "csv"})
    assert csv_r.status_code == 200 and csv_r.headers["content-type"].startswith("text/csv")
    text = csv_r.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Product,SKU")
    assert "'=cmd" in text and ",=cmd" not in text  # formula injection neutralised
    x = client.get("/api/v1/reports/profit", headers=admin, params={"period": "this_year", "format": "xlsx"})
    assert x.status_code == 200
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(x.content))
    assert wb.active.max_row >= 4
    for ds in ("products", "inventory", "customers", "suppliers", "sales", "purchases"):
        r = client.get(f"/api/v1/exports/{ds}", headers=admin, params={"format": "csv"})
        assert r.status_code == 200, (ds, r.text)
    assert client.get("/api/v1/exports/products", headers=cashier).status_code == 403
    assert client.get("/api/v1/exports/unknown", headers=admin).status_code == 404


def test_documents_pdf(client, admin, cashier, desk):
    prod = stock_product(client, admin, qty=5, price=100)
    sale = sell(client, cashier, prod["id"], 1).json()
    for path in (f"/sales/{sale['id']}/receipt.pdf", f"/sales/{sale['id']}/invoice.pdf", f"/purchases/{prod['po']['id']}/invoice.pdf",
                 f"/suppliers/{prod['supplier_id_used']}/statement.pdf"):
        r = client.get(f"/api/v1/documents{path}", headers=admin if "sales" not in path else cashier)
        assert r.status_code == 200 and r.content.startswith(b"%PDF"), path
    assert client.get(f"/api/v1/documents/purchases/{prod['po']['id']}/invoice.pdf", headers=cashier).status_code == 403


def test_global_search(client, admin, cashier, desk):
    prod = stock_product(client, admin, qty=5, name="Zanzibar Spice Mix")
    sale = sell(client, cashier, prod["id"], 1).json()
    r = client.get("/api/v1/search", headers=admin, params={"q": "zanzibar"}).json()
    assert r["products"][0]["title"] == "Zanzibar Spice Mix"
    r = client.get("/api/v1/search", headers=admin, params={"q": sale["invoice_number"]}).json()
    assert r["sales"][0]["title"] == sale["invoice_number"]
    r = client.get("/api/v1/search", headers=cashier, params={"q": "zanzibar"}).json()
    assert "suppliers" not in r and "employees" not in r
    assert client.get("/api/v1/search", headers=admin, params={"q": ""}).status_code == 422
    # SQL metacharacters are inert
    assert client.get("/api/v1/search", headers=admin, params={"q": "' OR 1=1 --"}).status_code == 200
    assert client.get("/api/v1/products", headers=admin, params={"search": "%_\\"}).status_code == 200


def test_notifications_lifecycle(client, admin, cashier):
    prod = stock_product(client, admin, qty=3, reorder_level=10, price=100)
    r = client.get("/api/v1/notifications", headers=admin, params={"type": "low_stock", "page_size": 100}).json()
    mine = [n for n in r["items"] if str(prod["id"]) == n["entity_id"]]
    assert mine and mine[0]["is_read"] is False and mine[0]["severity"] == "warning"
    count = client.get("/api/v1/notifications/unread-count", headers=admin).json()["count"]
    assert count > 0
    assert client.post(f"/api/v1/notifications/{mine[0]['id']}/read", headers=admin).status_code == 200
    assert client.get("/api/v1/notifications/unread-count", headers=admin).json()["count"] == count - 1
    # read state is per user
    again = client.get("/api/v1/notifications", headers=cashier, params={"type": "low_stock", "page_size": 100}).json()
    assert any(n["id"] == mine[0]["id"] and n["is_read"] is False for n in again["items"])
    assert client.post("/api/v1/notifications/read-all", headers=admin).status_code == 200
    assert client.get("/api/v1/notifications/unread-count", headers=admin).json()["count"] == 0
    # accountants have no inventory.read, so they never see stock alerts
    r2 = client.get("/api/v1/notifications", headers=cashier, params={"type": "supplier_due"}).json()
    assert r2["total"] == 0
