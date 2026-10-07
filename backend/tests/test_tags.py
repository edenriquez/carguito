"""Tags, the bridge, and the overlapping-dimension contract (B6).

The interesting assertion in here is not that tagging works. It is that a
transaction with two tags is counted **once** by a category breakdown and
**twice** by a tag breakdown, and that the second case says so in
``meta.overlapping`` -- because a client that averages or pie-charts an
overlapping breakdown without being told produces a chart summing past 100%.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from carguito.domain.entities import Category, Transaction
from carguito.domain.entities.tag import slugify
from carguito.domain.value_objects.enums import TxType

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def seeded(app):
    """One 400 expense in Comida and one 250 expense in Transporte."""
    container = app.extensions["container"]
    comida = Category(name="Comida")
    container.categories.add_many([comida])
    container.cube.sync_categories(container.categories.get_all())

    txs = [
        Transaction(
            user_id=DEV_USER,
            tx_date=date(2024, 1, 5),
            amount=Decimal("400"),
            raw_description="Vuelo Volaris",
            tx_type=TxType.EXPENSE,
            category_id=comida.id,
        ),
        Transaction(
            user_id=DEV_USER,
            tx_date=date(2024, 2, 10),
            amount=Decimal("250"),
            raw_description="Hotel",
            tx_type=TxType.EXPENSE,
            category_id=comida.id,
        ),
    ]
    container.transactions.add_many(txs)
    container.cube.upsert_transactions(txs)
    return {"comida": comida, "txs": txs}


def _tag(client, name, **extra):
    resp = client.post("/api/tags", json={"name": name, **extra})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _metric(client, metric, **extra):
    body = {"queries": [{"key": "k", "metric": metric, **extra}]}
    return client.post("/api/metrics/query", json=body).get_json()["results"]["k"]


# --- slugs ----------------------------------------------------------------
def test_slugify_folds_accents_so_near_duplicates_collide():
    """`Jubilación` and `jubilacion` are the same tag, not two identical-looking ones."""
    assert slugify("Jubilación") == slugify("jubilacion") == "jubilacion"
    assert slugify("Viaje  a  Japón!") == "viaje-a-japon"


# --- CRUD -----------------------------------------------------------------
def test_tag_crud(client):
    created = _tag(client, "Viaje a Japon", color="#ff5900", kind="investment")
    assert created["slug"] == "viaje-a-japon"
    assert created["kind"] == "investment"

    listed = client.get("/api/tags").get_json()
    assert listed["total"] == 1

    patched = client.patch(f"/api/tags/{created['id']}", json={"name": "Japon 2026"})
    assert patched.status_code == 200
    # The slug follows the name; leaving it behind would make the uniqueness
    # rule describe a name nobody can see any more.
    assert patched.get_json()["slug"] == "japon-2026"
    assert patched.get_json()["kind"] == "investment"

    deleted = client.delete(f"/api/tags/{created['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/tags").get_json()["total"] == 0


def test_duplicate_slug_for_one_user_is_a_409(client):
    _tag(client, "Viaje")
    # Different capitalisation, same slug.
    clash = client.post("/api/tags", json={"name": "viaje"})
    assert clash.status_code == 409


def test_slug_uniqueness_is_per_user_not_global(app, client):
    """Two people may both have a "viaje"; one person may not have two."""
    _tag(client, "Viaje")
    container = app.extensions["container"]
    from carguito.domain.entities import Tag

    # Another user's identically-slugged tag must be insertable.
    container.tags.add(Tag(user_id=uuid4(), name="Viaje"))
    assert client.get("/api/tags").get_json()["total"] == 1


def test_unknown_kind_is_a_400(client):
    assert client.post("/api/tags", json={"name": "X", "kind": "crypto"}).status_code == 400


def test_another_users_tag_is_a_404_not_a_403(app, client):
    from carguito.domain.entities import Tag

    theirs = Tag(user_id=uuid4(), name="Ajeno")
    app.extensions["container"].tags.add(theirs)

    assert client.patch(f"/api/tags/{theirs.id}", json={"name": "Mio"}).status_code == 404
    assert client.delete(f"/api/tags/{theirs.id}").status_code == 404
    assert app.extensions["container"].tags.get(theirs.id).name == "Ajeno"


# --- tagging --------------------------------------------------------------
def test_setting_tags_on_a_transaction_reaches_the_cube(client, seeded):
    viaje = _tag(client, "Viaje")
    tx = seeded["txs"][0]

    # Before: the metric has nothing to group by.
    assert _metric(client, "tag_totals")["rows"] == []

    resp = client.put(f"/api/transactions/{tx.id}/tags", json={"tag_ids": [viaje["id"]]})
    assert resp.status_code == 200

    result = _metric(client, "tag_totals")
    assert result["rows"] == [
        {"tag_id": viaje["id"], "tag": "Viaje", "expense_amount": "400.00"}
    ]
    # The transaction carries its tags on the way out too.
    listed = {t["id"]: t for t in client.get("/api/transactions").get_json()["items"]}
    assert listed[str(tx.id)]["tag_ids"] == [viaje["id"]]


def test_put_tags_replaces_rather_than_appends(client, seeded):
    a, b = _tag(client, "Viaje"), _tag(client, "Deducible")
    tx = seeded["txs"][0]

    client.put(f"/api/transactions/{tx.id}/tags", json={"tag_ids": [a["id"], b["id"]]})
    client.put(f"/api/transactions/{tx.id}/tags", json={"tag_ids": [b["id"]]})

    rows = _metric(client, "tag_totals")["rows"]
    assert [r["tag"] for r in rows] == ["Deducible"]


def test_bulk_tagging_is_additive_and_user_scoped(app, client, seeded):
    viaje, otro = _tag(client, "Viaje"), _tag(client, "Otro")
    first, second = seeded["txs"]
    client.put(f"/api/transactions/{first.id}/tags", json={"tag_ids": [otro["id"]]})

    # Include a transaction belonging to somebody else: it must be ignored, not
    # tagged, and not 404 the batch.
    theirs = Transaction(
        user_id=uuid4(),
        tx_date=date(2024, 1, 9),
        amount=Decimal("999"),
        raw_description="Ajeno",
        tx_type=TxType.EXPENSE,
    )
    app.extensions["container"].transactions.add_many([theirs])

    resp = client.post(
        f"/api/tags/{viaje['id']}/transactions",
        json={"transaction_ids": [str(first.id), str(second.id), str(theirs.id)]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["transactions_tagged"] == 2

    rows = {r["tag"]: r["expense_amount"] for r in _metric(client, "tag_totals")["rows"]}
    assert rows == {"Viaje": "650.00", "Otro": "400.00"}


def test_deleting_a_tag_keeps_the_transactions(client, seeded):
    viaje = _tag(client, "Viaje")
    tx = seeded["txs"][0]
    client.put(f"/api/transactions/{tx.id}/tags", json={"tag_ids": [viaje["id"]]})

    deleted = client.delete(f"/api/tags/{viaje['id']}")
    assert deleted.get_json()["transactions_untagged"] == 1

    # The annotation is gone; the money is not.
    assert _metric(client, "tag_totals")["rows"] == []
    assert _metric(client, "spend_by_category")["value"] == "650.00"
    assert client.get("/api/transactions").get_json()["items"][0]["tag_ids"] == []


# --- the overlapping contract --------------------------------------------
def test_two_tags_count_once_in_spend_but_twice_in_tag_totals(client, seeded):
    """The whole reason `meta.overlapping` exists."""
    viaje, deducible = _tag(client, "Viaje"), _tag(client, "Deducible")
    tx = seeded["txs"][0]
    client.put(
        f"/api/transactions/{tx.id}/tags",
        json={"tag_ids": [viaje["id"], deducible["id"]]},
    )

    # Category breakdown: the 400 is one transaction and is counted once.
    spend = _metric(client, "spend_by_category")
    assert spend["value"] == "650.00"
    assert spend["meta"]["overlapping"] is False

    # Tag breakdown: the same 400 appears under both tags.
    tags = _metric(client, "tag_totals")
    assert sorted((r["tag"], r["expense_amount"]) for r in tags["rows"]) == [
        ("Deducible", "400.00"),
        ("Viaje", "400.00"),
    ]
    # And the parts sum to 800 against a 650 period total -- which is *correct*,
    # and only readable as correct because of this flag.
    assert tags["meta"]["overlapping"] is True


def test_filtering_by_tag_does_not_fan_the_rows_out(client, seeded):
    """A tag *filter* uses the array column, so a two-tag row still counts once."""
    viaje, deducible = _tag(client, "Viaje"), _tag(client, "Deducible")
    tx = seeded["txs"][0]
    client.put(
        f"/api/transactions/{tx.id}/tags",
        json={"tag_ids": [viaje["id"], deducible["id"]]},
    )

    filtered = _metric(client, "spend_by_category", filters={"tag": viaje["id"]})
    assert filtered["value"] == "400.00"
    assert filtered["meta"]["source_txn_count"] == 1
    assert filtered["meta"]["overlapping"] is False

    # A list of tags is an OR, and still counts the transaction once.
    both = _metric(
        client, "spend_by_category", filters={"tag": [viaje["id"], deducible["id"]]}
    )
    assert both["value"] == "400.00"
    assert both["meta"]["source_txn_count"] == 1


def test_tag_is_not_a_dimension_of_spend_by_category(client, seeded):
    """The catalog stays closed: only `tag_totals` groups by tag."""
    result = _metric(client, "spend_by_category", dimensions=["tag"])
    assert result["error"]["code"] == "dimension_not_allowed"


def test_untagged_transactions_do_not_open_a_null_bucket(client, seeded):
    viaje = _tag(client, "Viaje")
    client.put(
        f"/api/transactions/{seeded['txs'][0].id}/tags", json={"tag_ids": [viaje["id"]]}
    )
    rows = _metric(client, "tag_totals")["rows"]
    # The 250 Hotel row is untagged and simply is not in a tag breakdown.
    assert [r["tag"] for r in rows] == ["Viaje"]


def test_rebuild_reproduces_the_bridge_and_the_labels(app, client, seeded):
    """The cube's tag_ids and bridge are derived; a rebuild must restore both."""
    viaje = _tag(client, "Viaje")
    client.put(
        f"/api/transactions/{seeded['txs'][0].id}/tags", json={"tag_ids": [viaje["id"]]}
    )

    app.extensions["container"].rebuild_cube.execute(user_id=DEV_USER)

    result = _metric(client, "tag_totals")
    assert result["rows"] == [
        {"tag_id": viaje["id"], "tag": "Viaje", "expense_amount": "400.00"}
    ]
    assert _metric(client, "spend_by_category", filters={"tag": viaje["id"]})["value"] == (
        "400.00"
    )


def test_deleting_a_statement_clears_its_bridge_rows(client, sample_cfdi_bytes):
    """Bridge cleanup is explicit: SQLite does not enforce ON DELETE CASCADE."""
    created = client.post(
        "/api/statements",
        data={"file": (sample_cfdi_bytes, "factura.xml")},
        content_type="multipart/form-data",
    )
    tx_id = client.get("/api/transactions").get_json()["items"][0]["id"]
    viaje = _tag(client, "Viaje")
    client.put(f"/api/transactions/{tx_id}/tags", json={"tag_ids": [viaje["id"]]})

    client.delete(f"/api/statements/{created.get_json()['statement_id']}")

    assert _metric(client, "tag_totals")["rows"] == []
    # And re-tagging something else later is not confused by a ghost row.
    assert client.get("/api/tags").get_json()["total"] == 1
