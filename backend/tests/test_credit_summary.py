"""The card figures a statement prints, read off its text."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from carguito.domain.services.credit_summary import read_credit_summary

CARD = """\
ESTADO DE CUENTA TARJETA DE CRÉDITO
Periodo del 12/AGO/2026 al 11/SEP/2026
RESUMEN
Saldo al corte $18,432.10
Pago mínimo $1,150.00
Pago para no generar intereses $18,432.10
Fecha límite de pago 01/OCT/2026
"""


def test_reads_the_three_figures():
    s = read_credit_summary(CARD)
    assert s is not None
    assert s.no_interest_payment == Decimal("18432.10")
    assert s.minimum_payment == Decimal("1150.00")
    assert s.due_date == date(2026, 10, 1)


def test_accepts_long_date_and_missing_accents():
    text = "PAGO PARA NO GENERAR INTERESES: $ 2,000.00\nFECHA LIMITE DE PAGO 15 de octubre de 2026"
    s = read_credit_summary(text)
    assert s is not None
    assert s.no_interest_payment == Decimal("2000.00")
    assert s.minimum_payment is None
    assert s.due_date == date(2026, 10, 15)


def test_numeric_month_and_two_digit_year():
    s = read_credit_summary("Fecha límite de pago 03/11/26")
    assert s is not None and s.due_date == date(2026, 11, 3)


def test_debit_statement_has_none():
    debit = "RESUMEN DEL 06/DIC/2025 AL 05/ENE/2026\n(-) 3 Retiros $40,365.23\nSALDO AL 05 DE ENERO DE 2026 $0.04"
    assert read_credit_summary(debit) is None
    assert read_credit_summary("") is None


def test_label_without_a_figure_is_absent_not_guessed():
    s = read_credit_summary("Pago mínimo\nVer detalle\nFecha límite de pago 01/OCT/2026")
    assert s is not None
    assert s.minimum_payment is None
    assert s.due_date == date(2026, 10, 1)
