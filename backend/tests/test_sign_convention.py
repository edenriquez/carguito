"""Regression tests for the sign contract (docs/redesign-plan.md §2).

``amount`` is a non-negative magnitude; ``tx_type`` alone carries direction.
Each test here pins one of the bugs that convention was introduced to kill.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from carguito.adapters.outbound.cube import DuckDbCube
from carguito.adapters.outbound.parsing import GenericBankParser, SatCfdiParser
from carguito.adapters.outbound.parsing.base import (
    SIGN_NEGATIVE,
    SIGN_NONE,
    SIGN_POSITIVE,
    find_amounts,
    infer_tx_type,
    parse_amount,
)
from carguito.adapters.outbound.persistence.db import Database
from carguito.adapters.outbound.persistence.migrator import upgrade_to_head
from carguito.application.dtos.extraction import ExtractedDocument
from carguito.domain.entities import Transaction
from carguito.domain.value_objects.enums import TxType


def _text_doc(lines: list[str]) -> ExtractedDocument:
    return ExtractedDocument(kind="text", filename="s.pdf", text="\n".join(lines), lines=lines)


def _cfdi(tipo: str, total: str = "1000.00") -> ExtractedDocument:
    xml = (
        '<?xml version="1.0"?>'
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        f'Total="{total}" Fecha="2024-05-01T10:00:00" TipoDeComprobante="{tipo}">'
        '<cfdi:Emisor Nombre="ACME SA DE CV" Rfc="ACM010101AAA"/>'
        "</cfdi:Comprobante>"
    )
    return ExtractedDocument(kind="xml", filename="f.xml", xml=xml)


# --- domain --------------------------------------------------------------
def test_negative_amount_raises_instead_of_being_absed():
    with pytest.raises(ValueError, match="non-negative magnitude"):
        Transaction(
            user_id=uuid4(),
            tx_date=date(2024, 1, 5),
            amount=Decimal("-45.50"),
            raw_description="OXXO",
            tx_type=TxType.EXPENSE,
        )


def test_signed_amount_reintroduces_direction():
    common = {"user_id": uuid4(), "tx_date": date(2024, 1, 5), "amount": Decimal("100.00")}
    expense = Transaction(raw_description="OXXO", tx_type=TxType.EXPENSE, **common)
    income = Transaction(raw_description="Nomina", tx_type=TxType.INCOME, **common)

    assert expense.amount == Decimal("100.00")
    assert expense.signed_amount == Decimal("-100.00")
    assert income.signed_amount == Decimal("100.00")


# --- parse_amount --------------------------------------------------------
@pytest.mark.parametrize(
    ("token", "sign_hint"),
    [
        ("(99.00)", SIGN_NEGATIVE),
        ("-99.00", SIGN_NEGATIVE),
        ("99.00", SIGN_NONE),
        ("+99.00", SIGN_POSITIVE),
        ("$99.00", SIGN_NONE),
    ],
)
def test_parse_amount_returns_magnitude_and_hint(token, sign_hint):
    magnitude, hint = parse_amount(token)
    assert magnitude == Decimal("99.00")
    assert hint == sign_hint


def test_find_amounts_yields_pairs():
    assert find_amounts("CARGO (99.00) SALDO 1,200.00") == [
        (Decimal("99.00"), SIGN_NEGATIVE),
        (Decimal("1200.00"), SIGN_NONE),
    ]


# --- infer_tx_type precedence: sign > keyword > default ------------------
def test_sign_hint_outranks_income_keyword():
    # "SPEI RECIBIDO" reads as income, but the statement marked it outgoing.
    assert infer_tx_type("SPEI RECIBIDO REVERSO", SIGN_NEGATIVE) == "expense"


def test_positive_sign_outranks_expense_default():
    assert infer_tx_type("DEVOLUCION TIENDA", SIGN_POSITIVE) == "income"


def test_keyword_used_when_no_sign_hint():
    assert infer_tx_type("SPEI RECIBIDO NOMINA", SIGN_NONE) == "income"
    assert infer_tx_type("STARBUCKS REFORMA", SIGN_NONE) == "expense"


# --- parser end to end ---------------------------------------------------
def test_parenthesised_expense_parses_as_positive_magnitude():
    stmt = GenericBankParser().parse(_text_doc(["05/01/2024 CARGO SERVICIO (99.00)"]))
    tx = stmt.transactions[0]
    assert tx.amount == Decimal("99.00")
    assert tx.tx_type == TxType.EXPENSE
    # And it survives the domain entity, which is what used to blow up.
    assert Transaction(
        user_id=uuid4(),
        tx_date=tx.tx_date,
        amount=tx.amount,
        raw_description=tx.raw_description,
        tx_type=tx.tx_type,
    ).signed_amount == Decimal("-99.00")


# --- CFDI TipoDeComprobante ----------------------------------------------
def test_nomina_cfdi_books_as_income():
    stmt = SatCfdiParser().parse(_cfdi("N", "18500.00"))
    assert len(stmt.transactions) == 1
    tx = stmt.transactions[0]
    assert tx.tx_type == TxType.INCOME
    assert tx.amount == Decimal("18500.00")


def test_egreso_cfdi_books_as_income():
    assert SatCfdiParser().parse(_cfdi("E")).transactions[0].tx_type == TxType.INCOME


def test_ingreso_cfdi_books_as_expense():
    assert SatCfdiParser().parse(_cfdi("I")).transactions[0].tx_type == TxType.EXPENSE


@pytest.mark.parametrize("tipo", ["P", "T"])
def test_non_monetary_cfdi_creates_no_transactions(tipo):
    stmt = SatCfdiParser().parse(_cfdi(tipo))
    assert stmt.transactions == []
    # The document is still parsed -- the upload is recorded, not dropped.
    assert stmt.bank == "SAT"
    assert stmt.period_start == date(2024, 5, 1)


# --- currency guard ------------------------------------------------------
def test_aggregates_do_not_sum_across_currencies():
    cube = DuckDbCube(":memory:")
    user = uuid4()
    cube.upsert_transactions(
        [
            Transaction(
                user_id=user,
                tx_date=date(2024, 1, 5),
                amount=Decimal(100),
                raw_description="OXXO",
                currency="MXN",
                tx_type=TxType.EXPENSE,
            ),
            Transaction(
                user_id=user,
                tx_date=date(2024, 1, 6),
                amount=Decimal(70),
                raw_description="AWS",
                currency="USD",
                tx_type=TxType.EXPENSE,
            ),
        ]
    )

    assert cube.spending_summary(user).total_expense == Decimal("100.00")
    assert cube.spending_summary(user, currency="USD").total_expense == Decimal("70.00")
    assert len(cube.spending_by_category(user)) == 1


# --- database constraint -------------------------------------------------
def test_check_constraint_rejects_negative_amounts(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'ck.db'}")
    upgrade_to_head(db)
    with db.engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        insert = text(
            "INSERT INTO transactions "
            "(id, user_id, tx_date, amount, currency, tx_type, status) "
            "VALUES ('t1', 'u1', '2024-01-05', :amount, 'MXN', 'expense', 'completed')"
        )
        with pytest.raises(Exception, match="(?i)constraint"):
            conn.execute(insert, {"amount": -1})


def test_backfill_repairs_existing_negative_rows(tmp_path):
    """A legacy database with a mis-signed row is repaired, not rejected."""
    db = Database(f"sqlite:///{tmp_path / 'legacy.db'}")

    from alembic import command

    from carguito.adapters.outbound.persistence.migrator import build_config

    config = build_config()
    with db.engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "0003")  # pre-CHECK schema

    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions "
                "(id, user_id, tx_date, amount, currency, tx_type, status) "
                "VALUES ('t1', 'u1', '2024-01-05', -250.00, 'MXN', 'expense', 'completed')"
            )
        )

    upgrade_to_head(db)

    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT amount FROM transactions")).scalar() == 250.00
