def test_cashier_cannot_manage_users(client, cashier):
    assert client.get("/api/v1/users", headers=cashier).status_code == 403
    r = client.post("/api/v1/users", headers=cashier, json={"email": "x@example.com", "full_name": "X Y", "password": "Abcdef-12", "role_ids": [1]})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_manager_cannot_manage_roles(client, manager):
    r = client.post("/api/v1/roles", headers=manager, json={"name": "x", "permissions": []})
    assert r.status_code == 403


def test_admin_cannot_assign_super_admin_role(client, admin):
    roles = client.get("/api/v1/roles", headers=admin).json()
    sa = next(r for r in roles if r["name"] == "SUPER_ADMIN")
    r = client.post("/api/v1/users", headers=admin, json={"email": "esc@example.com", "full_name": "Esc Alate", "password": "Abcdef-12", "role_ids": [sa["id"]]})
    assert r.status_code == 422


def test_custom_role_lifecycle_by_super_admin(client, tokens):
    h = tokens["SUPER_ADMIN"]
    r = client.post("/api/v1/roles", headers=h, json={"name": "shelf stocker", "description": "d", "permissions": ["product.read", "inventory.read"]})
    assert r.status_code == 201, r.text
    role = r.json()
    assert role["name"] == "SHELF_STOCKER"
    bad = client.post("/api/v1/roles", headers=h, json={"name": "bad", "permissions": ["not.real"]})
    assert bad.status_code == 422
    assert client.patch(f"/api/v1/roles/{role['id']}", headers=h, json={"permissions": ["product.read"]}).json()["permissions"] == ["product.read"]
    assert client.delete(f"/api/v1/roles/{role['id']}", headers=h).status_code == 200


def test_system_role_cannot_be_deleted_and_super_admin_immutable(client, tokens):
    h = tokens["SUPER_ADMIN"]
    roles = client.get("/api/v1/roles", headers=h).json()
    manager = next(r for r in roles if r["name"] == "MANAGER")
    assert client.delete(f"/api/v1/roles/{manager['id']}", headers=h).status_code == 422
    sa = next(r for r in roles if r["name"] == "SUPER_ADMIN")
    assert client.patch(f"/api/v1/roles/{sa['id']}", headers=h, json={"permissions": []}).status_code == 422


def test_permission_matrix_of_default_roles(client, tokens):
    def perms(role):
        return set(client.get("/api/v1/auth/me", headers=tokens[role]).json()["permissions"])

    cashier = perms("CASHIER")
    assert {"sale.create", "register.use"} <= cashier
    assert not ({"product.cost", "product.delete", "audit.read", "settings.update", "supplier.payment"} & cashier)
    assert "audit.read" in perms("ADMIN") and "backup.manage" not in perms("ADMIN")
    assert "backup.manage" in perms("SUPER_ADMIN")
    assert "report.finance" in perms("ACCOUNTANT") and "sale.create" not in perms("ACCOUNTANT")
    assert "inventory.adjust" in perms("INVENTORY_MANAGER") and "sale.create" not in perms("INVENTORY_MANAGER")
