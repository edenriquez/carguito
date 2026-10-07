"""The cube is derived state and must be provably disposable (plan §7, B2)."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from carguito.adapters.outbound.cube import DuckDbCube
from carguito.application.use_cases import RebuildCubeUseCase
from carguito.domain.entities import Transaction
from carguito.domain.value_objects.enums import TxType


def _tx(user, day, amount, tx_type=TxType.EXPENSE):
    return Transaction(
        user_id=user,
        tx_date=date(2024, 1, day),
        amount=Decimal(amount),
        raw_description=f"TX {day}",
        tx_type=tx_type,
    )


class _FakeTransactionRepo:
    """Stands in for SqlTransactionRepository's streaming read."""

    def __init__(self, rows):
        self._rows = rows

    def iter_for_user(self, user_id, *, batch_size=500):
        yield from (t for t in self._rows if t.user_id == user_id)


# --- the dead rollups are gone -------------------------------------------
def test_refresh_rollups_no_longer_exists():
    cube = DuckDbCube(":memory:")
    assert not hasattr(cube, "refresh_rollups")


def test_rollup_tables_are_not_created():
    cube = DuckDbCube(":memory:")
    cube.upsert_transactions([_tx(uuid4(), 5, "100")])
    tables = {r[0] for r in cube._con.execute("SHOW TABLES").fetchall()}
    assert "rollup_monthly" not in tables
    assert "rollup_category" not in tables
    assert "fact_transactions" in tables


def test_cube_writer_port_has_no_refresh_rollups():
    from carguito.application.ports.outbound import CubeWriter

    assert not hasattr(CubeWriter, "refresh_rollups")
    assert hasattr(CubeWriter, "rebuild_for_user")


# --- rebuild --------------------------------------------------------------
def _seed(cube, user):
    txs = [_tx(user, 5, "100"), _tx(user, 6, "300"), _tx(user, 7, "5000", TxType.INCOME)]
    cube.upsert_transactions(txs)
    return txs


def _fact_count(cube, user):
    return cube._con.execute(
        "SELECT COUNT(*) FROM fact_transactions WHERE user_id = ?", [str(user)]
    ).fetchone()[0]


def test_rebuild_restores_counts_after_manual_fact_deletion():
    cube = DuckDbCube(":memory:")
    user = uuid4()
    txs = _seed(cube, user)
    before = cube.spending_summary(user)
    assert _fact_count(cube, user) == 3

    cube._con.execute("DELETE FROM fact_transactions WHERE user_id = ?", [str(user)])
    assert _fact_count(cube, user) == 0
    assert cube.spending_summary(user).total_expense == Decimal(0)

    rows = cube.rebuild_for_user(user, iter(txs))

    assert rows == 3
    assert _fact_count(cube, user) == 3
    after = cube.spending_summary(user)
    assert after.total_expense == before.total_expense
    assert after.total_income == before.total_income


def test_rebuild_drops_facts_no_longer_backed_by_a_transaction():
    """A deleted statement's rows disappear on rebuild -- the point of B2."""
    cube = DuckDbCube(":memory:")
    user = uuid4()
    txs = _seed(cube, user)

    cube.rebuild_for_user(user, iter(txs[:1]))

    assert _fact_count(cube, user) == 1
    assert cube.spending_summary(user).total_expense == Decimal("100.00")


def test_rebuild_is_scoped_to_one_user():
    cube = DuckDbCube(":memory:")
    mine, theirs = uuid4(), uuid4()
    cube.upsert_transactions([_tx(mine, 5, "100"), _tx(theirs, 5, "999")])

    cube.rebuild_for_user(mine, iter([]))

    assert _fact_count(cube, mine) == 0
    assert _fact_count(cube, theirs) == 1


def test_rebuild_use_case_pulls_from_the_repository():
    cube = DuckDbCube(":memory:")
    user = uuid4()
    txs = _seed(cube, user)
    cube._con.execute("DELETE FROM fact_transactions")

    result = RebuildCubeUseCase(_FakeTransactionRepo(txs), cube).execute(user_id=user)

    assert result.rows == 3
    assert result.user_id == user
    assert cube.spending_summary(user).total_expense == Decimal("400.00")


# --- repository streaming -------------------------------------------------
def test_iter_for_user_streams_full_history_without_a_magic_limit(app):
    container = app.extensions["container"]
    repo = container.transactions
    user = uuid4()

    # More than list_for_user's default limit of 100.
    repo.add_many(
        [
            Transaction(
                user_id=user,
                tx_date=date(2024, 1, 1),
                amount=Decimal(1),
                raw_description=f"TX {i}",
            )
            for i in range(150)
        ]
    )

    assert len(repo.list_for_user(user)) == 100
    assert sum(1 for _ in repo.iter_for_user(user, batch_size=10)) == 150


# --- HTTP -----------------------------------------------------------------
def test_admin_rebuild_endpoint(client, sample_cfdi_bytes):
    upload = client.post(
        "/api/statements",
        data={"file": (sample_cfdi_bytes, "factura.xml")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201
    created = upload.get_json()["transactions_created"]
    assert created == 1

    response = client.post("/api/admin/cube/rebuild")

    assert response.status_code == 200
    body = response.get_json()
    assert body["rows"] == created
    assert body["user_id"]


def test_admin_rebuild_recovers_a_wiped_cube(client, app, sample_cfdi_bytes):
    client.post(
        "/api/statements",
        data={"file": (sample_cfdi_bytes, "factura.xml")},
        content_type="multipart/form-data",
    )
    cube = app.extensions["container"].cube
    cube._con.execute("DELETE FROM fact_transactions")

    assert client.post("/api/admin/cube/rebuild").get_json()["rows"] == 1

    summary = client.get("/api/analytics/summary").get_json()
    assert pytest.approx(summary["total_expense"]) == 500.0
