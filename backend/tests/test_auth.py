from tests.conftest import PASSWORD, ROLE_USERS


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["checks"]["database"] == "ok"


def test_login_success_returns_user_and_permissions(client):
    r = client.post("/api/v1/auth/login", json={"email": ROLE_USERS["CASHIER"], "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] and body["refresh_token"]
    assert "sale.create" in body["user"]["permissions"]
    assert "settings.update" not in body["user"]["permissions"]
    assert body["user"]["landing_path"] == "/dashboard"


def test_login_wrong_password_and_unknown_user_are_indistinguishable(client):
    a = client.post("/api/v1/auth/login", json={"email": ROLE_USERS["CASHIER"], "password": "nope-nope-1"})
    b = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-1"})
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["message"] == b.json()["error"]["message"]


def test_protected_endpoint_requires_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


def test_invalid_token_rejected(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_refresh_rotates_and_old_token_is_dead(client):
    login = client.post("/api/v1/auth/login", json={"email": ROLE_USERS["STAFF"], "password": PASSWORD}).json()
    old = login["refresh_token"]
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert r1.status_code == 200
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert r2.status_code == 401


def test_logout_revokes_session(client):
    login = client.post("/api/v1/auth/login", json={"email": ROLE_USERS["STAFF"], "password": PASSWORD}).json()
    h = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=h).status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401


def test_account_lockout_after_repeated_failures(client, admin):
    r = client.post(
        "/api/v1/users",
        headers=admin,
        json={"email": "lock@example.com", "full_name": "Lock Me", "password": "Lockme-123", "role_ids": [7]},
    )
    assert r.status_code == 201, r.text
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "lock@example.com", "password": "wrong-pass-1"})
    r = client.post("/api/v1/auth/login", json={"email": "lock@example.com", "password": "Lockme-123"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "account_locked"


def test_password_reset_flow(client, admin):
    client.post("/api/v1/users", headers=admin, json={"email": "reset@example.com", "full_name": "Reset Me", "password": PASSWORD, "role_ids": [7]})
    r = client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})
    token = r.json()["dev_token"]
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert unknown.status_code == 200 and "dev_token" not in unknown.json()
    bad = client.post("/api/v1/auth/reset-password", json={"token": "bad", "new_password": "Another-Pass-1"})
    assert bad.status_code == 422
    ok = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": PASSWORD})
    assert ok.status_code == 200
    again = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": PASSWORD})
    assert again.status_code == 422  # single use


def test_weak_password_rejected(client, admin):
    r = client.post(
        "/api/v1/users", headers=admin,
        json={"email": "weak@example.com", "full_name": "Weak Pass", "password": "12345678", "role_ids": [7]},
    )
    assert r.status_code == 422


def test_totp_login_flow(client, tokens):
    import pyotp

    h = tokens["STAFF"]
    setup = client.post("/api/v1/auth/2fa/setup", headers=h).json()
    code = pyotp.TOTP(setup["secret"]).now()
    assert client.post("/api/v1/auth/2fa/enable", headers=h, json={"code": code}).status_code == 200
    r = client.post("/api/v1/auth/login", json={"email": ROLE_USERS["STAFF"], "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "otp_required"
    r = client.post("/api/v1/auth/login", json={"email": ROLE_USERS["STAFF"], "password": PASSWORD, "otp": pyotp.TOTP(setup["secret"]).now()})
    assert r.status_code == 200
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.post("/api/v1/auth/2fa/disable", headers=h2, json={"code": pyotp.TOTP(setup["secret"]).now()}).status_code == 200
