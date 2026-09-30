from datetime import timedelta

from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, ROLE_USERS

BODY = {"X-Token-Delivery": "body"}  # API-client mode: refresh token in the JSON body instead of the cookie


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["checks"]["database"] == "ok"


def test_login_success_returns_user_and_permissions(client):
    r = client.post("/api/v1/auth/login", json={"email": ROLE_USERS["CASHIER"], "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] and body["refresh_token"] == ""  # refresh token travels only as an HttpOnly cookie
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


def test_refresh_rotates_and_old_token_is_dead(client, monkeypatch):
    from app.services import auth_service

    monkeypatch.setattr(auth_service, "ROTATION_GRACE", timedelta(seconds=0))
    login = client.post("/api/v1/auth/login", headers=BODY, json={"email": ROLE_USERS["STAFF"], "password": PASSWORD}).json()
    old = login["refresh_token"]
    r1 = client.post("/api/v1/auth/refresh", headers=BODY, json={"refresh_token": old})
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


def _fresh_client():
    from app.main import app

    return TestClient(app)


def test_browser_login_uses_httponly_cookie_and_hides_refresh_token_from_js():
    with _fresh_client() as c:
        r = c.post("/api/v1/auth/login", json={"email": ROLE_USERS["STAFF"], "password": PASSWORD})
        assert r.status_code == 200 and r.json()["refresh_token"] == ""
        cookie = r.headers["set-cookie"].lower()
        assert "ssm_refresh=" in cookie and "httponly" in cookie and "path=/api/v1/auth" in cookie and "samesite=lax" in cookie


def test_cookie_refresh_requires_csrf_header_and_rotates():
    with _fresh_client() as c:
        c.post("/api/v1/auth/login", json={"email": ROLE_USERS["STAFF"], "password": PASSWORD})
        no_header = c.post("/api/v1/auth/refresh")
        assert no_header.status_code == 401 and no_header.json()["error"]["code"] == "csrf_failed"
        ok = c.post("/api/v1/auth/refresh", headers={"X-Requested-With": "ssm"})
        assert ok.status_code == 200 and ok.json()["access_token"] and "ssm_refresh=" in ok.headers["set-cookie"]
        me = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ok.json()['access_token']}"})
        assert me.status_code == 200


def test_parallel_tabs_reusing_a_just_rotated_cookie_still_work():
    with _fresh_client() as c:
        c.post("/api/v1/auth/login", json={"email": ROLE_USERS["STAFF"], "password": PASSWORD})
        old_cookie = c.cookies.get("ssm_refresh")
        assert c.post("/api/v1/auth/refresh", headers={"X-Requested-With": "ssm"}).status_code == 200  # tab A
        c.cookies.set("ssm_refresh", old_cookie, path="/api/v1/auth")
        assert c.post("/api/v1/auth/refresh", headers={"X-Requested-With": "ssm"}).status_code == 200  # tab B, same cookie


def test_logged_out_or_expired_cookie_gets_no_grace_and_is_cleared():
    with _fresh_client() as c:
        login = c.post("/api/v1/auth/login", json={"email": ROLE_USERS["STAFF"], "password": PASSWORD}).json()
        cookie = c.cookies.get("ssm_refresh")
        out = c.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {login['access_token']}"})
        assert out.status_code == 200 and "max-age=0" in out.headers["set-cookie"].lower()
        c.cookies.set("ssm_refresh", cookie, path="/api/v1/auth")
        dead = c.post("/api/v1/auth/refresh", headers={"X-Requested-With": "ssm"})
        assert dead.status_code == 401 and dead.json()["error"]["code"] == "session_expired"


def test_password_change_revokes_refresh_cookie_immediately(client, admin):
    email = "cookie-pw@example.com"
    client.post("/api/v1/users", headers=admin, json={"email": email, "full_name": "Cookie Pw", "password": PASSWORD, "role_ids": [7]})
    with _fresh_client() as c:
        login = c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()
        h = {"Authorization": f"Bearer {login['access_token']}"}
        assert c.post("/api/v1/auth/change-password", headers=h, json={"current_password": PASSWORD, "new_password": "Brand-New-456"}).status_code == 200
        assert c.post("/api/v1/auth/refresh", headers={"X-Requested-With": "ssm"}).status_code == 401


def test_password_reset_email_is_really_sent_over_smtp_and_single_use(client, admin, monkeypatch):
    """End-to-end against a real local SMTP server: request -> email arrives -> link works once -> old link dead."""
    import re

    from aiosmtpd.controller import Controller

    from app.core.config import settings

    inbox = []

    class Sink:
        async def handle_DATA(self, server, session, envelope):  # noqa: N802
            from email import message_from_bytes, policy

            inbox.append((envelope.rcpt_tos, message_from_bytes(envelope.content, policy=policy.default).get_content()))  # decodes quoted-printable
            return "250 OK"

    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    ctl = Controller(Sink(), hostname="127.0.0.1", port=port)
    ctl.start()
    try:
        for k, v in {"smtp_host": "127.0.0.1", "smtp_port": port, "smtp_security": "none"}.items():
            monkeypatch.setattr(settings, k, v)
        email = "smtp-user@example.com"
        client.post("/api/v1/users", headers=admin, json={"email": email, "full_name": "Smtp User", "password": PASSWORD, "role_ids": [7]})
        client.post("/api/v1/auth/forgot-password", json={"email": email})
        client.post("/api/v1/auth/forgot-password", json={"email": email})  # second request retires the first link
        assert len(inbox) == 2 and inbox[0][0] == [email]
        links = [re.search(r"reset-password\?token=([\w\-]+)", body).group(1) for _, body in inbox]
        new_pw = "Fresh-Pass-789"
        stale = client.post("/api/v1/auth/reset-password", json={"token": links[0], "new_password": new_pw})
        assert stale.status_code == 422
        ok = client.post("/api/v1/auth/reset-password", json={"token": links[1], "new_password": new_pw})
        assert ok.status_code == 200
        assert client.post("/api/v1/auth/reset-password", json={"token": links[1], "new_password": "Other-Pass-321"}).status_code == 422
        assert client.post("/api/v1/auth/login", json={"email": email, "password": new_pw}).status_code == 200
        assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    finally:
        ctl.stop()


def test_smtp_failure_never_breaks_the_request(client, admin, monkeypatch):
    from app.core.config import settings

    for k, v in {"smtp_host": "127.0.0.1", "smtp_port": 1, "smtp_security": "none"}.items():  # nothing listens on port 1
        monkeypatch.setattr(settings, k, v)
    r = client.post("/api/v1/auth/forgot-password", json={"email": ROLE_USERS["STAFF"]})
    assert r.status_code == 200 and "reset link" in r.json()["message"]
