"""Workstations: CRUD, and the one property that matters more than CRUD.

That property is **a rule is only saveable if it is queryable** -- the same
guarantee `test_dashboards.py` holds for layouts. It matters more here: a widget
that cannot render is one broken card, while a rule that cannot compile is a
whole view whose every number is missing, with nothing on screen to say why.

So most of this file is about what the endpoint *refuses*.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from carguito.domain.entities import Transaction, WorkstationRule
from carguito.domain.value_objects.enums import TxType

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


def _create(client, **body):
    body.setdefault("name", "Recargas")
    body.setdefault("rule", {"description_contains": "recarga"})
    return client.post("/api/workstations", json=body)


# --- CRUD -----------------------------------------------------------------
def test_create_returns_the_rule_and_its_compiled_filters(client):
    resp = _create(
        client, name="Recargas", rule={"description_contains": "recarga", "amount_max": "300"}
    )
    assert resp.status_code == 201
    body = resp.get_json()

    assert body["name"] == "Recargas"
    assert body["rule"] == {"description_contains": "recarga", "amount_max": "300"}
    # The compiled form ships alongside the rule so no client reimplements the
    # translation and then disagrees about what "up to 300" means.
    assert body["filters"] == {"description_contains": "recarga", "amount_max": "300"}
    assert body["excluded_tx_ids"] == []


def test_list_order_is_stable_across_reads(client):
    """Newest first, ties broken alphabetically.

    Both of these are created inside the same second, and `created_at` has
    second granularity -- so this is the tie case, and what it must not do is
    come back in a different order each time. A sidebar that reshuffles between
    reads reads as the app losing track of the user's work.
    """
    _create(client, name="Zeta")
    _create(client, name="Alfa", rule={"description_contains": "uber"})

    first = [w["name"] for w in client.get("/api/workstations").get_json()["items"]]
    second = [w["name"] for w in client.get("/api/workstations").get_json()["items"]]

    assert first == second == ["Alfa", "Zeta"]


def test_get_reads_one_back(client):
    created = _create(client).get_json()
    fetched = client.get(f"/api/workstations/{created['id']}").get_json()
    assert fetched == created


def test_patch_leaves_omitted_fields_alone(client):
    created = _create(client, name="Recargas").get_json()

    renamed = client.patch(
        f"/api/workstations/{created['id']}", json={"name": "Recargas Telcel"}
    ).get_json()

    assert renamed["name"] == "Recargas Telcel"
    assert renamed["rule"] == created["rule"]  # untouched


def test_patch_replaces_the_rule_wholesale(client):
    created = _create(
        client, rule={"description_contains": "recarga", "amount_max": "300"}
    ).get_json()

    updated = client.patch(
        f"/api/workstations/{created['id']}", json={"rule": {"description_contains": "uber"}}
    ).get_json()

    # Not merged. A rule is one thought; half a new one over half an old one
    # describes a set nobody asked for.
    assert updated["rule"] == {"description_contains": "uber"}
    assert "amount_max" not in updated["filters"]


def test_delete_removes_it(client):
    created = _create(client).get_json()
    assert client.delete(f"/api/workstations/{created['id']}").status_code == 200
    assert client.get(f"/api/workstations/{created['id']}").status_code == 404
    assert client.get("/api/workstations").get_json()["total"] == 0


def test_unknown_id_is_a_404_on_every_verb(client):
    missing = uuid4()
    assert client.get(f"/api/workstations/{missing}").status_code == 404
    assert client.patch(f"/api/workstations/{missing}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/workstations/{missing}").status_code == 404


# --- a rule is only saveable if it is queryable ---------------------------
def test_an_undeclared_rule_condition_is_a_400(client):
    # `merchant` is not in the rule vocabulary. Accepting it and dropping it
    # would give the user a set quietly wider than the one they described.
    resp = _create(client, rule={"merchant": "telcel"})
    assert resp.status_code == 400


def test_a_rule_with_no_conditions_is_a_400(client):
    # That is the whole ledger wearing a name. Movimientos already shows it.
    assert _create(client, rule={}).status_code == 400


def test_an_empty_needle_is_a_400(client):
    # An empty needle matches every movement. A set that silently becomes "all
    # your money" is worse than a rejected save.
    assert _create(client, rule={"description_contains": "   "}).status_code == 400


def test_a_non_numeric_bound_is_a_400(client):
    assert _create(
        client, rule={"description_contains": "recarga", "amount_min": "mucho"}
    ).status_code == 400


def test_a_negative_bound_is_a_400(client):
    # Amounts are magnitudes in this domain; direction lives in tx_type. A
    # negative bound would silently match nothing.
    assert _create(
        client, rule={"description_contains": "recarga", "amount_min": "-5"}
    ).status_code == 400


def test_min_above_max_is_a_400(client):
    assert _create(
        client, rule={"description_contains": "r", "amount_min": "300", "amount_max": "10"}
    ).status_code == 400


def test_an_unnamed_workstation_is_a_400(client):
    assert client.post("/api/workstations", json={"rule": {"description_contains": "x"}}).status_code == 400


def test_an_unsupported_patch_field_is_a_400(client):
    created = _create(client).get_json()
    resp = client.patch(f"/api/workstations/{created['id']}", json={"user_id": str(uuid4())})
    assert resp.status_code == 400


def test_a_patch_that_would_break_the_rule_is_refused(client):
    created = _create(client).get_json()
    resp = client.patch(f"/api/workstations/{created['id']}", json={"rule": {"amount_min": "-1"}})
    assert resp.status_code == 400
    # And the stored rule is untouched -- a rejected edit must not half-apply.
    assert client.get(f"/api/workstations/{created['id']}").get_json()["rule"] == created["rule"]


# --- exclusions -----------------------------------------------------------
def test_exclusions_round_trip_deduplicated_and_ordered(client):
    a, b = str(uuid4()), str(uuid4())
    created = _create(client, excluded_tx_ids=[b, a, b]).get_json()

    # Order-independent and duplicate-free, or every diff between two saves of
    # the same set is noise.
    assert created["excluded_tx_ids"] == sorted({a, b})
    assert created["filters"]["exclude_tx"] == sorted({a, b})


def test_a_workstation_with_no_exclusions_carries_no_exclude_filter(client):
    # `exclude_tx: []` would be a predicate excluding nothing; leaving the key
    # out entirely is what the query layer expects.
    assert "exclude_tx" not in _create(client).get_json()["filters"]


def test_too_many_exclusions_is_refused(client):
    from carguito.domain.entities import MAX_EXCLUSIONS

    too_many = [str(uuid4()) for _ in range(MAX_EXCLUSIONS + 1)]
    resp = _create(client, excluded_tx_ids=too_many)
    # A lens with 200 exceptions is a list, and the rule under it is wrong.
    assert resp.status_code == 400


# --- the saved rule actually reads the ledger -----------------------------
@pytest.fixture
def ledger(app):
    container = app.extensions["container"]
    txs = [
        Transaction(
            user_id=DEV_USER,
            tx_date=date(2024, 1, day),
            amount=Decimal(amount),
            raw_description=description,
            tx_type=TxType.EXPENSE,
        )
        for day, amount, description in [
            (3, "15", "TELCEL RECARGA"),
            (10, "15", "TELCEL RECARGA"),
            (17, "200", "RECARGA PLAN"),
            (20, "450", "UBER TRIP"),
        ]
    ]
    container.transactions.add_many(txs)
    container.cube.upsert_transactions(txs)
    return txs


def test_the_saved_filters_are_accepted_verbatim_by_the_metric_endpoint(client, ledger):
    """The end of the whole design: what was saved is what can be queried.

    The client takes `filters` off the workstation and posts it unchanged. If
    the two vocabularies ever drift, this is what fails -- at the seam, not in
    a silently empty panel.
    """
    created = _create(
        client, rule={"description_contains": "recarga", "amount_max": "300"}
    ).get_json()

    resp = client.post(
        "/api/metrics/query",
        json={
            "period": {"start": "2024-01-01", "end": "2024-12-31"},
            "queries": [
                {"key": "p", "metric": "cohort_profile", "filters": created["filters"]}
            ],
        },
    )
    entry = resp.get_json()["results"]["p"]
    assert "error" not in entry, entry
    row = entry["rows"][0]
    # Both top-ups and the 200-peso plan (the bound is inclusive); not the Uber,
    # which the wording excludes.
    assert row["count"] == 3
    assert Decimal(row["total"]) == Decimal("230")


def test_exclusions_reach_the_metric_endpoint(client, ledger):
    created = _create(
        client,
        rule={"description_contains": "recarga"},
        excluded_tx_ids=[str(ledger[2].id)],  # the 200-peso plan
    ).get_json()

    resp = client.post(
        "/api/metrics/query",
        json={
            "period": {"start": "2024-01-01", "end": "2024-12-31"},
            "queries": [
                {"key": "p", "metric": "cohort_profile", "filters": created["filters"]}
            ],
        },
    )
    row = resp.get_json()["results"]["p"]["rows"][0]
    assert row["count"] == 2
    assert Decimal(row["total"]) == Decimal("30")


# --- the domain object on its own ----------------------------------------
def test_rule_to_filters_uses_the_catalog_names():
    rule = WorkstationRule(
        description_contains="recarga", amount_min="10", category_id=UUID(int=7)
    )
    filters = rule.to_filters([])
    # `category`, not `category_id`: the left-hand names here are the metric
    # catalog's, so drift is an import error rather than an empty widget.
    assert set(filters) == {"description_contains", "amount_min", "category"}
    assert filters["amount_min"] == "10"


def test_rule_amounts_survive_as_decimals_not_floats():
    rule = WorkstationRule(description_contains="x", amount_min="0.1", amount_max="0.3")
    # A bound that drifts by a centavo silently changes which movements are in
    # the set, which is why these travel as strings.
    assert rule.to_filters([])["amount_min"] == "0.1"
    # The conditions live on the clause; the rule is the union of clauses.
    assert rule.clauses[0].amount_min == Decimal("0.1")


# --- groups: several filters, unioned -------------------------------------
def test_one_filter_still_compiles_flat(client):
    """The back-compat property, stated as a test.

    Every lens saved before groups existed, and every one saved with a single
    filter after, must compile to the *same* query it always did -- no `any_of`
    wrapper, no new shape for a client to learn.
    """
    body = _create(client, rule={"description_contains": "recarga"}).get_json()
    assert body["rule"] == {"description_contains": "recarga"}
    assert body["filters"] == {"description_contains": "recarga"}


def test_a_group_round_trips_and_compiles_to_a_union(client):
    resp = _create(
        client,
        name="Suscripciones",
        rule={
            "any_of": [
                {"description_contains": "spotify"},
                {"description_contains": "netflix", "amount_max": "300"},
            ]
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["rule"] == {
        "any_of": [
            {"description_contains": "spotify"},
            {"description_contains": "netflix", "amount_max": "300"},
        ]
    }
    assert body["filters"] == {
        "any_of": [
            {"description_contains": "spotify"},
            {"description_contains": "netflix", "amount_max": "300"},
        ]
    }


def test_a_group_selects_the_union_through_the_metric_endpoint(client, ledger):
    """The property that makes groups worth having.

    Each filter carries its *own* bounds: the 100-peso cap applies to the
    top-ups and not to the Uber. Under one flat rule that is not expressible,
    which is why the user was previously forced into two lenses and mental
    arithmetic.
    """
    created = _create(
        client,
        rule={
            "any_of": [
                {"description_contains": "recarga", "amount_max": "100"},
                {"description_contains": "uber"},
            ]
        },
    ).get_json()

    resp = client.post(
        "/api/metrics/query",
        json={
            "period": {"start": "2024-01-01", "end": "2024-12-31"},
            "queries": [
                {"key": "p", "metric": "cohort_profile", "filters": created["filters"]}
            ],
        },
    )
    entry = resp.get_json()["results"]["p"]
    assert "error" not in entry, entry
    row = entry["rows"][0]
    # The two 15-peso top-ups and the 450 Uber. Not the 200-peso plan: it is
    # over the first filter's cap and the second filter never mentions it.
    assert row["count"] == 3
    assert Decimal(row["total"]) == Decimal("480")


def test_exclusions_apply_across_the_whole_group(client, ledger):
    """An exclusion says "not this movement", whichever filter let it in."""
    created = _create(
        client,
        rule={
            "any_of": [
                {"description_contains": "recarga", "amount_max": "100"},
                {"description_contains": "uber"},
            ]
        },
        excluded_tx_ids=[str(ledger[3].id)],  # the Uber
    ).get_json()

    resp = client.post(
        "/api/metrics/query",
        json={
            "period": {"start": "2024-01-01", "end": "2024-12-31"},
            "queries": [
                {"key": "p", "metric": "cohort_profile", "filters": created["filters"]}
            ],
        },
    )
    row = resp.get_json()["results"]["p"]["rows"][0]
    assert row["count"] == 2
    assert Decimal(row["total"]) == Decimal("30")


def test_an_empty_group_is_a_400(client):
    assert _create(client, rule={"any_of": []}).status_code == 400


def test_a_group_filter_with_no_conditions_is_a_400(client):
    assert _create(
        client, rule={"any_of": [{"description_contains": "x"}, {}]}
    ).status_code == 400


def test_a_group_alongside_a_flat_condition_is_a_400(client):
    """Half group, half flat has two readings, so it has none."""
    resp = _create(
        client,
        rule={"any_of": [{"description_contains": "x"}], "amount_max": "300"},
    )
    assert resp.status_code == 400


def test_an_undeclared_condition_inside_a_group_is_a_400(client):
    assert _create(
        client, rule={"any_of": [{"description_starts_with": "x"}]}
    ).status_code == 400


def test_a_nested_group_is_a_400(client):
    """One level of union. A tree is a query language, and this is not one."""
    resp = _create(
        client, rule={"any_of": [{"any_of": [{"description_contains": "x"}]}]}
    )
    assert resp.status_code == 400


def test_too_many_filters_in_one_group_is_a_400(client):
    from carguito.domain.entities import MAX_CLAUSES

    resp = _create(
        client,
        rule={"any_of": [{"description_contains": f"x{i}"} for i in range(MAX_CLAUSES + 1)]},
    )
    assert resp.status_code == 400


def test_an_inverted_bound_inside_a_group_is_a_400(client):
    resp = _create(
        client,
        rule={"any_of": [{"description_contains": "x", "amount_min": "300", "amount_max": "10"}]},
    )
    assert resp.status_code == 400
