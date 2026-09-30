import sqlite3

from tests.helpers import stock_of, uid


def _csv(*lines: str) -> dict:
    return {"file": ("data.csv", ("\n".join(lines) + "\n").encode("utf-8"), "text/csv")}


def test_product_import_dry_run_reports_every_error(client, admin):
    n = uid()
    rows = ["sku,name,unit,selling_price,barcode,opening_stock,category",
            f"IMP-{n}-1,Good Item,Piece,120,BC{n}1,25,Import Cat",
            f"IMP-{n}-2,Bad Price,Piece,abc,,,",
            f"IMP-{n}-3,Bad Unit,Furlong,10,,,",
            f"IMP-{n}-1,Dup In File,Piece,10,,,",
            f"IMP-{n}-5,Neg Price,Piece,-4,,,"]
    r = client.post("/api/v1/admin/import/products", headers=admin, data={"dry_run": "true"}, files=_csv(*rows)).json()
    assert r["committed"] is False and r["valid_rows"] == 1 and r["error_count"] == 4
    assert sorted(e["row"] for e in r["errors"]) == [3, 4, 5, 6]
    assert client.get("/api/v1/products", headers=admin, params={"search": f"IMP-{n}"}).json()["total"] == 0  # nothing written


def test_product_import_commit_all_or_nothing_then_skip_invalid(client, admin):
    n = uid()
    good = f"IMP2-{n}-1,Widget,Piece,50,BCX{n}1,10,Imported"
    bad = f"IMP2-{n}-2,Broken,Piece,zzz,,,"
    hdr = "sku,name,unit,selling_price,barcode,opening_stock,category"
    blocked = client.post("/api/v1/admin/import/products", headers=admin, data={"dry_run": "false"}, files=_csv(hdr, good, bad)).json()
    assert blocked["committed"] is False and blocked["imported"] == 0
    ok = client.post("/api/v1/admin/import/products", headers=admin, data={"dry_run": "false", "skip_invalid": "true"}, files=_csv(hdr, good, bad)).json()
    assert ok["committed"] is True and ok["imported"] == 1 and ok["error_count"] == 1
    prod = client.get("/api/v1/products", headers=admin, params={"search": f"IMP2-{n}-1"}).json()["items"][0]
    assert prod["category"]["name"] == "Imported" and stock_of(client, admin, prod["id"]) == 10
    again = client.post("/api/v1/admin/import/products", headers=admin, data={"dry_run": "true"}, files=_csv(hdr, good)).json()
    assert again["error_count"] == 1 and "already exists" in again["errors"][0]["message"]


def test_import_rejects_bad_files(client, admin, cashier):
    assert client.post("/api/v1/admin/import/products", headers=admin, files=_csv("name,unit")).status_code == 422  # missing columns
    assert client.post("/api/v1/admin/import/products", headers=admin, files=_csv("sku,name,unit,selling_price,evil", "a,b,Piece,1,2")).status_code == 422
    assert client.post("/api/v1/admin/import/products", headers=admin, files={"file": ("x.csv", b"\xff\xfe\x00bad", "text/csv")}).status_code == 422
    assert client.post("/api/v1/admin/import/products", headers=admin, files={"file": ("big.csv", b"sku,name,unit,selling_price\n" + b"a" * (3 * 1024 * 1024), "text/csv")}).status_code == 422
    assert client.post("/api/v1/admin/import/products", headers=cashier, files=_csv("sku,name,unit,selling_price")).status_code == 403
    assert client.get("/api/v1/admin/import/products/template", headers=admin).status_code == 200


def test_customer_and_supplier_import(client, admin):
    n = uid()
    r = client.post("/api/v1/admin/import/customers", headers=admin, data={"dry_run": "false"},
                    files=_csv("name,phone,credit_limit,opening_balance", f"Imported Cust,0175{n}0001,5000,300")).json()
    assert r["imported"] == 1
    cust = client.get("/api/v1/customers", headers=admin, params={"search": f"0175{n}0001"}).json()["items"][0]
    assert cust["balance"] == 300 and cust["credit_limit"] == 5000
    r = client.post("/api/v1/admin/import/suppliers", headers=admin, data={"dry_run": "false"},
                    files=_csv("name,phone,opening_balance", f"Imported Sup,0176{n}0001,900")).json()
    assert r["imported"] == 1
    dup = client.post("/api/v1/admin/import/customers", headers=admin, data={"dry_run": "true"},
                      files=_csv("name,phone", f"Dup,0175{n}0001")).json()
    assert dup["error_count"] == 1


def test_backup_create_list_download_and_permissions(client, tokens):
    sa, admin = tokens["SUPER_ADMIN"], tokens["ADMIN"]
    assert client.post("/api/v1/admin/backups", headers=admin).status_code == 403
    assert client.get("/api/v1/admin/backups", headers=tokens["MANAGER"]).status_code == 403
    r = client.post("/api/v1/admin/backups", headers=sa)
    assert r.status_code == 201, r.text
    name = r.json()["name"]
    assert name in [b["name"] for b in client.get("/api/v1/admin/backups", headers=sa).json()]
    d = client.get(f"/api/v1/admin/backups/{name}/download", headers=sa)
    from app.core.config import settings

    assert d.status_code == 200 and (d.content.startswith(b"SQLite format 3") if settings.is_sqlite else d.content.startswith(b"PGDMP"))
    assert client.get("/api/v1/admin/backups/..%2f..%2fetc%2fpasswd/download", headers=sa).status_code in (404, 422)
    assert client.get("/api/v1/admin/backups/evil.db/download", headers=sa).status_code == 422
    assert client.post(f"/api/v1/admin/backups/{name}/restore", headers=sa, json={"confirm": "wrong"}).status_code == 422
    assert client.post(f"/api/v1/admin/backups/{name}/restore", headers=tokens["ADMIN"], json={"confirm": name}).status_code == 403


def test_backup_restore_roundtrip(tmp_path, monkeypatch):
    from sqlalchemy import create_engine

    from app.core import database
    from app.core.config import settings
    from app.services import backup_service

    db_file = tmp_path / "live.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "bk"))
    monkeypatch.setattr(database, "engine", create_engine(settings.database_url))
    con = sqlite3.connect(db_file)
    con.execute("CREATE TABLE t (v TEXT)")
    con.execute("INSERT INTO t VALUES ('before')")
    con.commit()
    con.close()
    path = backup_service.create_backup()
    con = sqlite3.connect(db_file)
    con.execute("UPDATE t SET v='after'")
    con.commit()
    con.close()
    backup_service.restore_backup(path.name)
    con = sqlite3.connect(db_file)
    assert con.execute("SELECT v FROM t").fetchone()[0] == "before"
    con.close()
    assert any("prerestore" in b["name"] for b in backup_service.list_backups())


def test_employee_privacy_and_activity(client, admin, tokens):
    r = client.post("/api/v1/employees", headers=admin, json={"full_name": "Rahim Uddin", "phone": "01712345678", "position": "Cashier", "salary": 25000, "national_id": "1234567890"})
    assert r.status_code == 201, r.text
    emp = r.json()
    assert emp["employee_code"].startswith("EMP-") and emp["salary"] == 25000
    mgr = tokens["MANAGER"]  # can read employees but not salaries
    got = client.get(f"/api/v1/employees/{emp['id']}", headers=mgr).json()
    assert got["salary"] is None and got["national_id"] is None
    assert client.patch(f"/api/v1/employees/{emp['id']}", headers=mgr, json={"salary": 99999}).status_code == 403
    assert client.get("/api/v1/employees", headers=tokens["CASHIER"]).status_code == 403
    assert client.patch(f"/api/v1/employees/{emp['id']}", headers=admin, json={"salary": 27000}).status_code == 200
    logs = client.get("/api/v1/audit-logs", headers=admin, params={"action": "employee.salary_change"}).json()["items"]
    assert logs[0]["old_value"]["salary"] == "25000.00" and logs[0]["new_value"]["salary"] == "27000.00"
    ci = client.post(f"/api/v1/employees/{emp['id']}/attendance/check-in", headers=admin)
    assert ci.status_code == 201
    assert client.post(f"/api/v1/employees/{emp['id']}/attendance/check-in", headers=admin).status_code == 409
    assert client.post(f"/api/v1/employees/{emp['id']}/attendance/check-out", headers=admin).status_code == 200
    assert client.get(f"/api/v1/employees/{emp['id']}/activity", headers=admin).status_code == 200
    bad = client.post("/api/v1/employees", headers=admin, json={"full_name": "X", "phone": "abc"})
    assert bad.status_code == 422


def test_audit_log_is_read_only_and_restricted(client, admin, cashier, tokens):
    assert client.get("/api/v1/audit-logs", headers=cashier).status_code == 403
    assert client.get("/api/v1/audit-logs", headers=tokens["ACCOUNTANT"]).status_code == 403
    for method in ("post", "put", "patch", "delete"):
        r = getattr(client, method)("/api/v1/audit-logs", headers=admin)
        assert r.status_code in (404, 405)
        r = getattr(client, method)("/api/v1/audit-logs/1", headers=admin)
        assert r.status_code in (404, 405)


def test_settings_permissions_and_validation(client, admin, cashier, manager):
    pub = client.get("/api/v1/settings/public").json()
    assert "shop.name" in pub and "inventory.allow_oversell" not in pub
    assert client.put("/api/v1/settings", headers=cashier, json={"values": {"shop.name": "Hacked"}}).status_code == 403
    assert client.put("/api/v1/settings", headers=manager, json={"values": {"shop.name": "Hacked"}}).status_code == 403
    assert "inventory.allow_oversell" not in client.get("/api/v1/settings", headers=cashier).json()
    assert client.put("/api/v1/settings", headers=admin, json={"values": {"made.up": 1}}).status_code == 422
    assert client.put("/api/v1/settings", headers=admin, json={"values": {"pos.cashier_max_discount_percent": 250}}).status_code == 422
    assert client.put("/api/v1/settings", headers=admin, json={"values": {"locale.timezone": "Mars/Base"}}).status_code == 422
    ok = client.put("/api/v1/settings", headers=admin, json={"values": {"shop.name": "Bazaar Super Shop"}})
    assert ok.status_code == 200 and ok.json()["shop.name"] == "Bazaar Super Shop"
    logs = client.get("/api/v1/audit-logs", headers=admin, params={"action": "settings.update"}).json()["items"]
    assert logs[0]["new_value"]["shop.name"] == "Bazaar Super Shop"


def test_tax_rate_configuration_and_effective_dates(client, admin):
    from tests.helpers import stock_product

    r = client.post("/api/v1/tax-rates", headers=admin, json={"name": "Future VAT", "rate": 20, "effective_from": "2999-01-01"})
    assert r.status_code == 201
    future = r.json()
    prod = stock_product(client, admin, qty=5, price=120, tax_rate_id=future["id"])
    prev = client.post("/api/v1/sales/preview", headers=admin, json={"items": [{"product_id": prod["id"], "quantity": 1}]})
    assert prev.status_code == 200 and prev.json()["tax_total"] == 0  # not yet effective
    client.put(f"/api/v1/tax-rates/{future['id']}", headers=admin, json={"name": "Now VAT", "rate": 20, "effective_from": "2000-01-01"})
    prev = client.post("/api/v1/sales/preview", headers=admin, json={"items": [{"product_id": prod["id"], "quantity": 1}]}).json()
    assert prev["tax_total"] == 20 and prev["grand_total"] == 120  # 120 incl. 20% => 100 + 20
    assert client.post("/api/v1/tax-rates", headers=admin, json={"name": "Bad", "rate": 150}).status_code == 422


def test_users_cannot_be_used_after_deactivation(client, admin):
    from tests.conftest import PASSWORD

    r = client.post("/api/v1/users", headers=admin, json={"email": f"temp{uid()}@example.com", "full_name": "Temp User", "password": PASSWORD, "role_ids": [7]})
    user = r.json()
    login = client.post("/api/v1/auth/login", json={"email": user["email"], "password": PASSWORD}).json()
    h = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200
    assert client.patch(f"/api/v1/users/{user['id']}", headers=admin, json={"is_active": False}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401  # sessions revoked immediately
    assert client.post("/api/v1/auth/login", json={"email": user["email"], "password": PASSWORD}).status_code == 401


def test_security_headers_cors_and_error_shape(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    ok = client.options("/api/v1/auth/login", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    evil = client.options("/api/v1/auth/login", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in evil.headers
    e = client.get("/api/v1/products/abc", headers={"Authorization": "Bearer x"})
    assert set(e.json()["error"]) >= {"code", "message"}
    assert "Traceback" not in e.text
