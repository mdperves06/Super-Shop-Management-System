"""Failure-path behaviour: bad tokens, broken requests, outages and throttling all fail gracefully."""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.middleware.common import RateLimitMiddleware
from tests.conftest import PASSWORD, ROLE_USERS
from tests.helpers import ensure_register_open, make_customer, sell, stock_product


def _token(user_id: int, *, kind="access", secret=None, minutes=30, sid=None):
    now = datetime.now(UTC)
    return jwt.encode({"sub": str(user_id), "type": kind, "sid": sid, "iat": now, "exp": now + timedelta(minutes=minutes)},
                      secret or settings.jwt_secret, algorithm="HS256")


def test_expired_token_is_rejected_with_a_specific_code(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {_token(1, minutes=-5)}"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"


def test_tampered_and_wrong_type_tokens_are_rejected(client):
    good = _token(1)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {good[:-3]}xyz"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {_token(1, secret='not-the-secret')}"}).status_code == 401
    # a refresh token must never work as an access token (and vice versa)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {_token(1, kind='refresh', secret=settings.refresh_token_secret)}"}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": good}).status_code == 401
    # "alg: none" style forgery
    forged = jwt.encode({"sub": "1", "type": "access"}, key="", algorithm="none")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_malformed_requests_get_a_clean_error_shape(client, admin):
    r = client.post("/api/v1/products", headers={**admin, "Content-Type": "application/json"}, content=b"{not json")
    assert r.status_code == 422 and "error" in r.json()
    r = client.post("/api/v1/products", headers=admin, json=["wrong", "shape"])
    assert r.status_code == 422
    r = client.get("/api/v1/products", headers=admin, params={"page": "abc"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert client.get("/api/v1/no-such-route", headers=admin).json()["error"]["code"] == "http_error"
    assert client.delete("/api/v1/auth/login", headers=admin).status_code == 405
    body = client.get("/api/v1/products/999999", headers=admin)
    assert body.status_code == 404 and "Traceback" not in body.text


def test_sale_with_invalid_customer_or_payment_method(client, admin, cashier):
    ensure_register_open(client, cashier, 100)
    prod = stock_product(client, admin, qty=5)
    base = {"items": [{"product_id": prod["id"], "quantity": 1}]}
    bad_customer = client.post("/api/v1/sales", headers=cashier, json={**base, "customer_id": 999999, "payments": [{"payment_method_id": 1, "amount": 150}]})
    assert bad_customer.status_code == 422 and bad_customer.json()["error"]["code"] == "invalid_customer"
    bad_method = client.post("/api/v1/sales", headers=cashier, json={**base, "payments": [{"payment_method_id": 999999, "amount": 150}]})
    assert bad_method.status_code == 422 and bad_method.json()["error"]["code"] == "invalid_payment_method"
    assert client.post("/api/v1/sales", headers=cashier, json={**base, "payments": [{"payment_method_id": 1, "amount": -5}]}).status_code == 422
    inactive = make_customer(client, admin)
    client.patch(f"/api/v1/customers/{inactive['id']}", headers=admin, json={"is_active": False})
    assert client.post("/api/v1/sales", headers=cashier, json={**base, "customer_id": inactive["id"], "payments": [{"payment_method_id": 1, "amount": 150}]}).status_code == 422
    assert sell(client, cashier, prod["id"], 1).status_code == 201  # and a valid sale still works afterwards


def test_health_reports_degraded_when_database_is_down(client, monkeypatch):
    from app import main
    from app.core import database

    class Boom:
        def connect(self):
            raise RuntimeError("database unreachable")

    monkeypatch.setattr(main, "engine", Boom())
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["checks"]["database"] == "unavailable" and r.json()["status"] == "degraded"
    assert "unreachable" not in r.text  # internals are not leaked
    monkeypatch.undo()
    assert client.get("/health").status_code == 200
    assert database.engine is not None


def test_unhandled_errors_return_generic_500_without_internals(monkeypatch):
    from app.main import create_app

    app = create_app()

    @app.get("/boom")
    def boom():  # noqa: ANN202
        raise RuntimeError("secret internal detail: password=hunter2")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/boom")
    assert r.status_code == 500
    body = r.json()["error"]
    assert body["code"] == "internal_error" and "hunter2" not in r.text and "Traceback" not in r.text and body["request_id"]


def test_rate_limiter_throttles_and_login_is_stricter():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, per_minute=5, login_per_minute=2)

    @app.get("/api/v1/thing")
    def thing():  # noqa: ANN202
        return {"ok": True}

    @app.post("/api/v1/auth/login")
    def login():  # noqa: ANN202
        return {"ok": True}

    with TestClient(app) as c:
        assert [c.get("/api/v1/thing").status_code for _ in range(6)] == [200] * 5 + [429]
        assert c.post("/api/v1/auth/login").status_code == 200
        assert c.post("/api/v1/auth/login").status_code == 200
        blocked = c.post("/api/v1/auth/login")
        assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "rate_limited" and blocked.headers["retry-after"]


def test_password_is_never_logged_or_returned(client, caplog):
    caplog.set_level("DEBUG")
    r = client.post("/api/v1/auth/login", json={"email": ROLE_USERS["MANAGER"], "password": PASSWORD})
    assert PASSWORD not in r.text
    assert PASSWORD not in caplog.text
    users = client.get("/api/v1/users", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert "password" not in users.text and "argon2" not in users.text
