"""Transaction safety, concurrency and migration integrity."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from tests.helpers import ensure_register_open, make_customer, payment_method_id, sell, stock_of, stock_product


@pytest.fixture(scope="module")
def desks(client, admin, cashier, manager):
    if not any(r["name"] == "Counter 2" for r in client.get("/api/v1/registers", headers=admin).json()):
        client.post("/api/v1/registers", headers=admin, json={"name": "Counter 2"})
    ensure_register_open(client, cashier, 1000)
    ensure_register_open(client, manager, 1000, register="Counter 2")


def test_concurrent_sales_never_oversell(client, admin, cashier, manager, desks, db_session):
    from app.models.sales import Sale

    prod = stock_product(client, admin, qty=5, price=100)
    users = [cashier, manager] * 4  # 8 simultaneous buyers, 5 units

    def buy(headers):
        return sell(client, headers, prod["id"], 1, pay=100)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(buy, users))
    codes = sorted(r.status_code for r in results)
    assert codes.count(201) == 5 and codes.count(409) == 3, codes
    assert stock_of(client, admin, prod["id"]) == 0
    invoices = [r.json()["invoice_number"] for r in results if r.status_code == 201]
    assert len(set(invoices)) == 5  # numbering is collision-free under concurrency
    batches = client.get("/api/v1/inventory/batches", headers=admin, params={"product_id": prod["id"], "include_empty": True}).json()["items"]
    assert all(b["quantity_remaining"] >= 0 for b in batches)


def test_two_cashiers_competing_for_last_units(client, admin, cashier, manager, desks):
    prod = stock_product(client, admin, qty=5, price=100)

    def buy(headers):
        return sell(client, headers, prod["id"], 5, pay=500)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.map(buy, [cashier, manager])
    assert sorted([a.status_code, b.status_code]) == [201, 409]
    assert stock_of(client, admin, prod["id"]) == 0


def test_oversell_allowed_only_when_enabled(client, admin, cashier, desks):
    prod = stock_product(client, admin, qty=2, price=100)
    assert sell(client, cashier, prod["id"], 3, pay=300).status_code == 409
    client.put("/api/v1/settings", headers=admin, json={"values": {"inventory.allow_oversell": True}})
    try:
        r = sell(client, cashier, prod["id"], 3, pay=300)
        assert r.status_code == 201, r.text
        assert stock_of(client, admin, prod["id"]) == -1
    finally:
        client.put("/api/v1/settings", headers=admin, json={"values": {"inventory.allow_oversell": False}})


def test_failure_after_stock_and_payment_writes_rolls_everything_back(client, admin, manager, desks, db_session, monkeypatch):
    """If the ledger step blows up the invoice, stock movement, payment and cash row must all vanish."""
    from app.models.finance import CashTransaction
    from app.models.inventory import InventoryTransaction
    from app.models.sales import Sale, SalePayment
    from app.services import ledger

    prod = stock_product(client, admin, qty=10, price=100)
    cust = make_customer(client, admin)

    def counts():
        out = (db_session.scalar(select(func.count()).select_from(Sale)), db_session.scalar(select(func.count()).select_from(SalePayment)),
               db_session.scalar(select(func.count()).select_from(CashTransaction)),
               db_session.scalar(select(func.count()).select_from(InventoryTransaction)))
        db_session.rollback()
        return out

    before = counts()

    def boom(*a, **k):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(ledger, "post_customer", boom)
    with pytest.raises(RuntimeError):
        sell(client, manager, prod["id"], 2, pay=200, customer_id=cust["id"])
    monkeypatch.undo()
    assert counts() == before
    assert stock_of(client, admin, prod["id"]) == 10


def test_product_stock_always_equals_batch_sum(client, admin, db_session):
    from app.models.inventory import Inventory, InventoryBatch

    rows = db_session.execute(
        select(Inventory.product_id, Inventory.current_stock, func.coalesce(func.sum(InventoryBatch.quantity_remaining), 0))
        .outerjoin(InventoryBatch, InventoryBatch.product_id == Inventory.product_id).group_by(Inventory.product_id, Inventory.current_stock)).all()
    db_session.rollback()
    mismatched = [(pid, Decimal(str(cur)), Decimal(str(s))) for pid, cur, s in rows if Decimal(str(cur)) != Decimal(str(s)) and Decimal(str(cur)) >= 0]
    assert not mismatched, mismatched


def test_ledger_balance_equals_running_total(client, admin, db_session):
    from app.models.customers import Customer, CustomerTransaction
    from app.models.purchasing import Supplier, SupplierTransaction

    for model, txn, fk in ((Customer, CustomerTransaction, CustomerTransaction.customer_id), (Supplier, SupplierTransaction, SupplierTransaction.supplier_id)):
        sums = dict(db_session.execute(select(fk, func.sum(txn.amount)).group_by(fk)).all())
        for party in db_session.scalars(select(model)):
            expected = Decimal(str(sums.get(party.id, 0) or 0))
            assert Decimal(str(party.balance)) == expected, (model.__name__, party.id)
    db_session.rollback()


def test_alembic_migrations_match_models(tmp_path):
    """The migration chain must produce exactly the schema the models declare."""
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    import app.models  # noqa: F401
    from app.core.config import BASE_DIR
    from app.core.database import Base

    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff
    command.downgrade(cfg, "base")


def test_foreign_keys_enforced(db_session):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db_session.execute(text("INSERT INTO sale_items (sale_id, product_id, product_name, sku, quantity, unit_price, line_total) "
                                "VALUES (999999, 999999, 'x', 'x', 1, 1, 1)"))
    db_session.rollback()
