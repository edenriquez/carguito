"""PATCH /api/transactions/{id} -- the first way to correct anything (B5).

The assertions that matter are not "the field changed": they are that the
correction is *recorded as a correction* (``category_source``), that it reaches
analytics without waiting for a rebuild, and that another user's row is
indistinguishable from a missing one.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from carguito.domain.entities import Category, Transaction
from carguito.domain.value_objects.enums import TxType

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def fixtures(app):
    """One 100 MXN expense in Comida, plus an empty Transporte to move it to."""
    container = app.extensions["container"]
    comida = Category(name="Comida")
    transporte = Category(name="Transporte")
    container.categories.add_many([comida, transporte])
    container.cube.sync_categories(container.categories.get_all())

    tx = Transaction(
        user_id=DEV_USER,
        tx_date=date(2024, 1, 5),
        amount=Decimal("100"),
        raw_description="OXXO SUC 4412",
        tx_type=TxType.EXPENSE,
        category_id=comida.id,
    )
    container.transactions.add_many([tx])
    container.cube.upsert_transactions([tx])
    return {"tx": tx, "comida": comida, "transporte": transporte}


def _spend_rows(client):
    body = {"queries": [{"key": "k", "metric": "spend_by_category"}]}
    return client.post("/api/metrics/query", json=body).get_json()["results"]["k"]


def test_patch_category_flips_source_to_user_and_moves_the_cube(client, fixtures):
    tx, transporte = fixtures["tx"], fixtures["transporte"]

    assert [r["category"] for r in _spend_rows(client)["rows"]] == ["Comida"]

    resp = client.patch(
        f"/api/transactions/{tx.id}", json={"category_id": str(transporte.id)}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["category_id"] == str(transporte.id)
    # The whole reason the column exists: a later re-classification pass must be
    # able to tell a human decision from its own guess.
    assert body["category_source"] == "user"

    # Written straight through to the cube -- a correction that does not move
    # the number on screen reads as a bug.
    rows = _spend_rows(client)["rows"]
    assert [r["category"] for r in rows] == ["Transporte"]
    assert rows[0]["expense_amount"] == "100.00"


def test_patch_persists_description_notes_and_exclusion(client, fixtures):
    tx = fixtures["tx"]
    resp = client.patch(
        f"/api/transactions/{tx.id}",
        json={
            "description": "Cafe con Ana",
            "notes": "reembolsable",
            "excluded_from_stats": True,
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["description"] == "Cafe con Ana"
    assert body["notes"] == "reembolsable"
    assert body["excluded_from_stats"] is True
    # Not a category edit, so the source stays the classifier's.
    assert body["category_source"] == "auto"

    listed = client.get("/api/transactions").get_json()["items"][0]
    assert listed["notes"] == "reembolsable"
    assert listed["excluded_from_stats"] is True


def test_excluded_from_stats_removes_the_row_from_spend(client, fixtures):
    """The exclusion is a measure-level default filter, not a per-metric one."""
    tx = fixtures["tx"]
    assert _spend_rows(client)["value"] == "100.00"

    client.patch(f"/api/transactions/{tx.id}", json={"excluded_from_stats": True})

    result = _spend_rows(client)
    assert result["rows"] == []
    # No rows means no claim: never a confident "0.00".
    assert result["value"] is None


def test_patching_another_users_transaction_is_a_404_not_a_403(app, client, fixtures):
    """Non-disclosure: a 403 would confirm the id exists."""
    container = app.extensions["container"]
    theirs = Transaction(
        user_id=uuid4(),
        tx_date=date(2024, 1, 9),
        amount=Decimal("999"),
        raw_description="Ajeno",
        tx_type=TxType.EXPENSE,
    )
    container.transactions.add_many([theirs])

    resp = client.patch(f"/api/transactions/{theirs.id}", json={"notes": "mio"})
    assert resp.status_code == 404
    # And it really was left alone.
    assert container.transactions.get(theirs.id).notes is None


def test_patching_a_missing_transaction_is_a_404(client, fixtures):
    resp = client.patch(
        "/api/transactions/2b1f9a3c-0000-4000-8000-000000000000", json={"notes": "x"}
    )
    assert resp.status_code == 404


def test_unknown_category_is_a_400(client, fixtures):
    """The transaction was found; the category the client named does not exist."""
    resp = client.patch(
        f"/api/transactions/{fixtures['tx'].id}", json={"category_id": str(uuid4())}
    )
    assert resp.status_code == 400
    assert client.get("/api/transactions").get_json()["items"][0]["category_source"] == "auto"


def test_unsupported_field_is_rejected(client, fixtures):
    """Amount, date and direction belong to the statement, not to the user."""
    resp = client.patch(f"/api/transactions/{fixtures['tx'].id}", json={"amount": 1})
    assert resp.status_code == 400


def test_omitting_a_key_leaves_it_alone_but_null_clears_it(client, fixtures):
    tx = fixtures["tx"]
    client.patch(f"/api/transactions/{tx.id}", json={"notes": "algo"})
    # `description` was never mentioned, so it survives.
    after = client.patch(f"/api/transactions/{tx.id}", json={"category_id": None}).get_json()
    assert after["notes"] == "algo"
    assert after["description"] == "OXXO SUC 4412"
    # An explicit null is a real instruction: clear the category.
    assert after["category_id"] is None
    assert after["category_source"] == "user"


def test_rebuild_preserves_the_edit(app, client, fixtures):
    """The cube is disposable: a rebuild must reproduce the correction."""
    tx, transporte = fixtures["tx"], fixtures["transporte"]
    client.patch(f"/api/transactions/{tx.id}", json={"category_id": str(transporte.id)})

    app.extensions["container"].rebuild_cube.execute(user_id=DEV_USER)

    assert [r["category"] for r in _spend_rows(client)["rows"]] == ["Transporte"]
