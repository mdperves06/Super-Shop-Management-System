import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="shoptest_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTO_MIGRATE"] = "false"
os.environ["UPLOAD_DIR"] = str(Path(_tmp, "uploads"))
os.environ["BACKUP_DIR"] = str(Path(_tmp, "backups"))
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "100000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app, initialise_database  # noqa: E402
from app.models.auth import Role  # noqa: E402
from app.services import auth_service  # noqa: E402

PASSWORD = "Test-Pass-123"
ROLE_USERS = {
    "SUPER_ADMIN": "superadmin@example.com",
    "ADMIN": "admin@example.com",
    "MANAGER": "manager@example.com",
    "CASHIER": "cashier@example.com",
    "INVENTORY_MANAGER": "inventory@example.com",
    "ACCOUNTANT": "accountant@example.com",
    "STAFF": "staff@example.com",
}


@pytest.fixture(scope="session", autouse=True)
def _database():
    initialise_database()
    with SessionLocal() as db:
        for role_name, email in ROLE_USERS.items():
            role = db.scalar(select(Role).where(Role.name == role_name))
            auth_service.create_user(db, email=email, full_name=role_name.title(), password=PASSWORD, role_ids=[role.id])
        db.commit()
    yield


@pytest.fixture(scope="session")
def client(_database):
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def tokens(client):
    return {role: _login(client, email) for role, email in ROLE_USERS.items()}


@pytest.fixture(scope="session")
def admin(tokens):
    return tokens["ADMIN"]


@pytest.fixture(scope="session")
def manager(tokens):
    return tokens["MANAGER"]


@pytest.fixture(scope="session")
def cashier(tokens):
    return tokens["CASHIER"]


@pytest.fixture(scope="session")
def db_session():
    with SessionLocal() as db:
        yield db
