"""Transfer and cash-withdrawal flags (B7): heuristics, ingest, metrics, backfill.

The heuristics are unit-tested against wording that actually appears on Mexican
statements, because the failure modes are asymmetric and both are silent:
over-matching transfers deletes real spending from every total, and
under-splitting fees inflates "cash withdrawn" with money that never left the
ATM.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import inspect, text

from carguito.adapters.outbound.persistence.db import Database
from carguito.adapters.outbound.persistence.migrator import upgrade_to_head
from carguito.domain.entities import Transaction
from carguito.domain.services.flags import detect_flags
from carguito.domain.value_objects.enums import TxType

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


# --- heuristics -----------------------------------------------------------
@pytest.mark.parametrize(
    "description",
    [
        "PAGO TC BBVA",
        "pago tarjeta de credito banamex",
        "PAGO TDC 5678",
        "TRASPASO ENTRE CUENTAS PROPIAS",
        "Pago de TC Santander",
        # The card statement acknowledging the payment YOU made into it — the
        # incoming half of a self-transfer (real Banamex wording).
        "29-jun-2026 SU ABONO...GRACIAS -",
        # Nu's own savings pocket: money to/from it never left the user.
        "07-may-2026 Retiro de Cajita: Mis domingos",
        "Deposito en Cajita: Vacaciones",
    ],
)
def test_explicit_card_payments_and_traspasos_are_transfers(description):
    assert detect_flags(description).is_transfer is True


@pytest.mark.parametrize(
    "description",
    [
        # A SPEI to a third party is rent, a friend, a contractor -- real money
        # leaving. Calling it an internal transfer would silently delete a large
        # share of someone's spending, and silently is the problem.
        "TRANSFERENCIA SPEI A JUAN PEREZ",
        "SPEI ENVIADO BANORTE",
        "TRANSFERENCIA INTERBANCARIA",
        "PAGO SERVICIO CFE",
        "PAGO OXXO",
        "OXXO SUC 4412",
        # "abono nomina" is salary, not a self-transfer — the "su" is the anchor.
        "ABONO NOMINA QUINCENA 12",
    ],
)
def test_plain_transfers_and_ordinary_payments_are_not_transfers(description):
    assert detect_flags(description).is_transfer is False


@pytest.mark.parametrize(
    "description",
    [
        "RETIRO CAJERO BANAMEX 4412",
        "RETIRO SIN TARJETA",
        "DISP EFECTIVO",
        "DISPOSICION DE EFECTIVO",
        "RETIRO ATM AEROPUERTO",
        "retiro en cajero automatico",
    ],
)
def test_cash_withdrawals_are_detected(description):
    assert detect_flags(description).is_cash_withdrawal is True


@pytest.mark.parametrize(
    "description",
    [
        # The bank's charge for the withdrawal is not the cash.
        "COMISION RETIRO",
        "COMISIÓN RETIRO CAJERO OTRO BANCO",
        "IVA COMISION RETIRO",
        "COMISIONES CAJERO",
    ],
)
def test_withdrawal_fees_are_not_withdrawn_cash(description):
    assert detect_flags(description).is_cash_withdrawal is False


@pytest.mark.parametrize(
    "description", ["FARMACIA GUADALAJARA", "STARBUCKS REFORMA", "NETFLIX.COM"]
)
def test_ordinary_purchases_carry_neither_flag(description):
    flags = detect_flags(description)
    assert (flags.is_transfer, flags.is_cash_withdrawal) == (False, False)


def test_accents_and_spacing_do_not_change_the_answer():
    assert detect_flags("  PAGO   TC   BBVA ").is_transfer is True
    assert detect_flags("Comisión  Retiro").is_cash_withdrawal is False


def test_atm_is_matched_as_a_word_not_a_substring():
    """An unanchored 'atm' would fire on any description containing the letters."""
    assert detect_flags("FLATMATE RENT").is_cash_withdrawal is False


def test_a_cajita_retiro_is_a_transfer_not_a_withdrawal():
    """'Retiro de Cajita' moves money between the user's own pockets — no
    bill left an ATM, and counting it as cash would inflate metric 4."""
    flags = detect_flags("07-may-2026 Retiro de Cajita: Mis domingos")
    assert flags.is_transfer is True
    assert flags.is_cash_withdrawal is False


def test_a_withdrawal_is_not_also_a_transfer():
    flags = detect_flags("RETIRO CAJERO BANAMEX 4412")
    assert (flags.is_transfer, flags.is_cash_withdrawal) == (False, True)


# --- flags through the metric layer --------------------------------------
@pytest.fixture
def seeded(app):
    """One card payment, one ATM withdrawal, one fee, one ordinary purchase."""
    container = app.extensions["container"]
    txs = [
        Transaction(
            user_id=DEV_USER,
            tx_date=date(2024, 1, 5),
            amount=Decimal("3000"),
            raw_description="PAGO TC BBVA",
            tx_type=TxType.EXPENSE,
            is_transfer=True,
        ),
        Transaction(
            user_id=DEV_USER,
            tx_date=date(2024, 1, 10),
            amount=Decimal("2000"),
            raw_description="RETIRO CAJERO BANAMEX 4412",
            tx_type=TxType.EXPENSE,
            is_cash_withdrawal=True,
        ),
        Transaction(
            user_id=DEV_USER,
            tx_date=date(2024, 1, 10),
            amount=Decimal("35"),
            raw_description="COMISION RETIRO",
            tx_type=TxType.EXPENSE,
        ),
        Transaction(
            user_id=DEV_USER,
            tx_date=date(2024, 2, 3),
            amount=Decimal("500"),
            raw_description="OXXO SUC 4412",
            tx_type=TxType.EXPENSE,
        ),
        Transaction(
            user_id=DEV_USER,
            tx_date=date(2024, 2, 15),
            amount=Decimal("9000"),
            raw_description="NOMINA",
            tx_type=TxType.INCOME,
        ),
    ]
    container.transactions.add_many(txs)
    container.cube.upsert_transactions(txs)
    return txs


def _metric(client, metric, **extra):
    body = {"queries": [{"key": "k", "metric": metric, **extra}]}
    return client.post("/api/metrics/query", json=body).get_json()["results"]["k"]


def test_a_transfer_is_excluded_from_spend_and_cash_flow(client, seeded):
    """The 3000 card payment is the card's charges again; counting it doubles them."""
    spend = _metric(client, "spend_by_category")
    # 2000 withdrawal + 35 fee + 500 OXXO. Not the 3000.
    assert spend["value"] == "2535.00"
    assert spend["meta"]["source_txn_count"] == 3

    flow = {r["month"]: r for r in _metric(client, "monthly_cash_flow")["rows"]}
    assert flow["2024-01"]["expense_amount"] == "2035.00"
    assert flow["2024-02"]["income_amount"] == "9000.00"


def test_a_withdrawal_is_cash_withdrawn_and_still_counts_as_spend(client, seeded):
    """A withdrawal is not a transfer: the money really did leave the account.

    It is only the *category* that is unknown, which is why this is a flag.
    """
    withdrawn = _metric(client, "cash_withdrawn")
    assert withdrawn["rows"] == [{"month": "2024-01", "withdrawal_amount": "2000.00"}]
    assert withdrawn["value"] == "2000.00"

    # And the same 2000 is still inside total spend.
    assert Decimal(_metric(client, "spend_by_category")["value"]) >= Decimal("2000")


def test_the_withdrawal_fee_is_not_counted_as_withdrawn_cash(client, seeded):
    """35 pesos of commission never reached anybody's pocket."""
    assert _metric(client, "cash_withdrawn")["value"] == "2000.00"


def test_cash_withdrawn_is_published_as_an_estimate(client):
    """The heuristic reads free text, so the header tag is not optional."""
    by_id = {i["id"]: i for i in client.get("/api/metrics").get_json()["items"]}
    assert by_id["cash_withdrawn"]["quality"] == "estimate"
    assert by_id["spend_by_category"]["quality"] is None


def test_lifetime_flow_ignores_the_request_period(client, seeded):
    """All-time by definition; narrowing it would answer a different question."""
    narrow = _metric(
        client, "lifetime_flow", period={"start": "2024-02-01", "end": "2024-02-29"}
    )
    row = narrow["rows"][0]
    assert row["income_amount"] == "9000.00"
    # January's withdrawal and fee are present despite the February period.
    assert row["expense_amount"] == "2535.00"
    assert row["net_amount"] == "6465.00"
    # And the card payment inflates neither side.
    assert "3000" not in row["expense_amount"]

    by_id = {i["id"]: i for i in client.get("/api/metrics").get_json()["items"]}
    assert by_id["lifetime_flow"]["ignores_period"] is True


def test_excluded_rows_stay_excluded_from_cash_withdrawn(client, seeded):
    withdrawal = seeded[1]
    client.patch(f"/api/transactions/{withdrawal.id}", json={"excluded_from_stats": True})
    result = _metric(client, "cash_withdrawn")
    assert result["rows"] == []
    assert result["value"] is None


# --- ingest ---------------------------------------------------------------
def test_ingest_sets_both_flags(app, client, sample_cfdi_bytes):
    """The flags are derived once, at ingest, so every later read agrees."""
    client.post(
        "/api/statements",
        data={"file": (sample_cfdi_bytes, "factura.xml")},
        content_type="multipart/form-data",
    )
    container = app.extensions["container"]
    stored = container.transactions.list_for_user(DEV_USER)
    assert len(stored) == 1
    # "OXXO" is neither, and gets explicit False rather than NULL.
    assert stored[0].is_transfer is False
    assert stored[0].is_cash_withdrawal is False


def test_seed_no_longer_files_withdrawals_under_transfers(app):
    """A withdrawal's category is unknown; it is a flag, not a category (§2)."""
    labels = {
        c.name: c.categorization_labels
        for c in app.extensions["container"].categories.get_all()
    }
    transfers = labels["Transferencias & Ajustes"]
    assert "retiro" not in transfers
    assert "cajero" not in transfers
    # The wording that genuinely is an internal movement lives on the leaf.
    assert "pago tc" in labels["Pago de tarjeta"]
    assert "pago tc" not in transfers


# --- the backfill ---------------------------------------------------------
def test_migration_backfills_flags_on_pre_existing_rows(tmp_path):
    """Existing history must mean the same thing as anything uploaded after 0008."""
    db = Database(f"sqlite:///{tmp_path / 'backfill.db'}")

    # Bring the schema to 0007 -- the last revision before the flags exist.
    from alembic import command

    from carguito.adapters.outbound.persistence.migrator import _run, build_config

    _run(build_config(), db, command.upgrade, "0007")

    with db.engine.begin() as conn:
        assert "is_transfer" not in {
            c["name"] for c in inspect(db.engine).get_columns("transactions")
        }
        for tx_id, description in (
            ("11111111-1111-4111-8111-111111111111", "PAGO TC BBVA"),
            ("22222222-2222-4222-8222-222222222222", "RETIRO CAJERO BANAMEX 4412"),
            ("33333333-3333-4333-8333-333333333333", "COMISION RETIRO"),
            ("44444444-4444-4444-8444-444444444444", "OXXO SUC 4412"),
        ):
            conn.execute(
                text(
                    "INSERT INTO transactions "
                    "(id, user_id, tx_date, raw_description, description, amount, "
                    " currency, tx_type, status, category_source, excluded_from_stats) "
                    "VALUES (:id, :user, '2024-01-05', :d, :d, 100, 'MXN', 'expense', "
                    "'completed', 'auto', 0)"
                ),
                {"id": tx_id, "user": str(DEV_USER), "d": description},
            )

    upgrade_to_head(db)

    with db.engine.connect() as conn:
        flags = {
            row[0]: (bool(row[1]), bool(row[2]))
            for row in conn.execute(
                text("SELECT raw_description, is_transfer, is_cash_withdrawal FROM transactions")
            )
        }
    assert flags == {
        "PAGO TC BBVA": (True, False),
        "RETIRO CAJERO BANAMEX 4412": (False, True),
        # The fee is neither -- the backfill runs the same rule as ingest.
        "COMISION RETIRO": (False, False),
        "OXXO SUC 4412": (False, False),
    }
