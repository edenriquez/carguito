"""The Banamex debit ("MiCuenta") layout: one movement is a block, not a line.

The fixture is synthetic but shape-faithful to real statements: a page-1
opening balance cut off by a page break, header furniture between pages, a
block whose amount line lands on the next page, a zero-amount notice, the two
collapsed columns, a December inside a statement cut in January, and a trailing
section after the detail. Every one of these broke a first draft.

The check that matters is the last one: the parse must reconcile against the
statement's own summary totals. A parser that reads 18 of 19 withdrawals is
not "mostly right"; the missing one is the largest, by construction.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from carguito.adapters.outbound.extraction.classifier import KeywordTemplateClassifier, TEMPLATE_BANAMEX
from carguito.adapters.outbound.parsing import BanamexParser
from carguito.application.dtos.extraction import ExtractedDocument
from carguito.domain.value_objects.enums import TxType

PAGE_1 = """\
ESTADO DE CUENTA AL 05 DE ENERO DE 2026
CLIENTE: 100000001
Página: 1 de 3
Suc. 384 MARIANO ESCOBED,CDMX MiCuenta
FULANA DE TAL PEREZ
RESUMEN GENERAL
PRODUCTO/SERVICIO CONTRATO SALDO ANTERIOR SALDO AL 05/ENE/2026
MiCuenta 90000000001 $0.57 $0.04
RESUMEN DEL 06/DIC/2025 AL 05/ENE/2026
Saldo Anterior $0.57
(+) 2 Depósitos $40,364.70
(-) 3 Retiros $40,365.23
SALDO AL 05 DE ENERO DE 2026 $0.04
DETALLE DE OPERACIONES
FECHA CONCEPTO RETIROS DEPOSITOS SALDO
06 DIC SALDO ANTERIOR 0.57
"""

PAGE_2 = """\
ESTADO DE CUENTA AL 05 DE ENERO DE 2026
CLIENTE: 100000001
Página: Centro de Atención Telefónica 2 de 3
Ciudad de México: 55 0000 0000
FULANA DE TAL PEREZ
Resto del país: 800 000 0000
DETALLE DE OPERACIONES
FECHA CONCEPTO RETIROS DEPOSITOS SALDO
08 DIC EXENCION COBRO COMISION
PENALIZACION POR NO MANTENER
EL SALDO PROMEDIO MINIMO
CAJA 0071 AUT 00148249
HORA 03:38 SUC 0511 0.57
15 DIC PAGO RECIBIDO DE SIST TRANSF Y
PAGOS POR ORDEN DE EMPRESA
EJEMPLO SA DE CV CTA.ORDENANTE
646180000000000000 REF.0251215
SUC 0
CAJA 0 AUT 0 HORA 0: 0
Nomina 2Q Diciembre RASTREO:
SO1032512151400495209
CAJA 0078 AUT 01411819
HORA 14:01 SUC 0859 39,864.70 39,865.27
15 DIC PAGO DE SERVICIO 161770 A TB
5400000000000000
SUC 0870
CAJA 0071 AUT 00161770 HORA 11:55 8,400.00 31,465.27
15 DIC PAGO INTERBANCARIO A NU MEXICO
AL BENEF.
FULANA,DE TAL/PEREZ (DATO
NO VERIFICADO POR ESTA
INSTITUCION) CTA.BENEFICIARIO
638180000000000000 CLAVE
SUC 0
CAJA 0 AUT 0 HORA 0: 0
RASTREO 085907757790336457
REF. 0151225 Transferencia
interbancaria MISMO DIA
CAJA 0071 AUT 00775779
000191.B01EJDA013.OD.0105.01
"""

PAGE_3 = """\
ESTADO DE CUENTA AL 05 DE ENERO DE 2026
CLIENTE: 100000001
Página: 3 de 3
FULANA DE TAL PEREZ
DETALLE DE OPERACIONES
FECHA CONCEPTO RETIROS DEPOSITOS SALDO
HORA 13:30 SUC 0870 31,465.00 0.27
02 ENE PAGO RECIBIDO DE NU MEXICO POR
ORDEN DE FULANA DE TAL PEREZ
CTA.ORDENANTE
638180000000000000 REF.0020126
Transferencia RASTREO:
NU395S51FQKF91VBM7SQ53U7D6T6
CAJA 0078 AUT 00361448
HORA 09:47 SUC 0859 500.00 500.27
02 ENE DIS.EFE. CAJERO EJEMPLO
75430065339464910004998
SUC 0342
CAJA 0088 AUT 00436389 HORA 14:38 500.23 0.04
000191.B01EJDA013.OD.0105.01
GRAFICO TRANSACCIONAL
Retiros 3 40,365.23
"""


def _doc(text: str) -> ExtractedDocument:
    return ExtractedDocument(kind="text", filename="bnmx.pdf", text=text, lines=text.splitlines())


def _parse():
    return BanamexParser().parse(_doc(PAGE_1 + PAGE_2 + PAGE_3))


def test_the_debit_layout_reconciles_against_its_own_summary():
    stmt = _parse()
    deposits = [t for t in stmt.transactions if t.tx_type == TxType.INCOME]
    withdrawals = [t for t in stmt.transactions if t.tx_type == TxType.EXPENSE]
    assert (len(deposits), sum(t.amount for t in deposits)) == (2, Decimal("40364.70"))
    assert (len(withdrawals), sum(t.amount for t in withdrawals)) == (3, Decimal("40365.23"))


def test_direction_comes_from_the_balance_not_the_wording():
    """"PAGO RECIBIDO" is a deposit and "PAGO DE SERVICIO" a withdrawal, but
    neither word decides it: the balance moved up by one and down by the other."""
    by_desc = {t.raw_description[:25]: t for t in _parse().transactions}
    assert by_desc["PAGO RECIBIDO DE SIST TRA"].tx_type == TxType.INCOME
    assert by_desc["PAGO DE SERVICIO 161770 A"].tx_type == TxType.EXPENSE


def test_a_block_that_crosses_a_page_break_keeps_its_amount_and_loses_the_header():
    stmt = _parse()
    (spei,) = [t for t in stmt.transactions if "INTERBANCARIO" in t.raw_description]
    assert spei.amount == Decimal("31465.00")
    assert spei.tx_date == date(2025, 12, 15)
    # The customer's name and "Página:" sit between the block's lines on paper;
    # neither reaches the description.
    assert "FULANA DE TAL PEREZ" not in spei.raw_description
    assert "Página" not in spei.raw_description
    assert "CLIENTE" not in spei.raw_description


def test_the_year_rolls_back_for_months_after_the_cut():
    stmt = _parse()
    assert stmt.period_start == date(2025, 12, 6)
    assert stmt.period_end == date(2026, 1, 5)
    dates = sorted({t.tx_date for t in stmt.transactions})
    assert dates[0].year == 2025 and dates[-1] == date(2026, 1, 2)


def test_zero_amount_notices_and_the_opening_balance_are_not_movements():
    descriptions = " | ".join(t.raw_description for t in _parse().transactions)
    assert "EXENCION" not in descriptions
    assert "SALDO ANTERIOR" not in descriptions


def test_descriptions_keep_the_counterparty_and_the_concept_and_drop_the_plumbing():
    (nomina,) = [t for t in _parse().transactions if "Nomina" in t.raw_description]
    assert "EMPRESA EJEMPLO SA DE CV" in nomina.raw_description
    assert "Nomina 2Q Diciembre" in nomina.raw_description
    for plumbing in ("CAJA 0078", "HORA 14:01", "RASTREO", "SO1032512151400495209"):
        assert plumbing not in nomina.raw_description


def test_the_classifier_routes_a_debit_statement_to_the_banamex_parser():
    text = PAGE_1 + PAGE_2 + PAGE_3 + "\\nBanco Nacional de México, S.A. Grupo Financiero Banamex\\n"
    assert KeywordTemplateClassifier().classify(_doc(text)) == TEMPLATE_BANAMEX


def test_the_card_layout_still_parses_line_by_line():
    """The other Banamex statement: dated one-liners. Unchanged."""
    stmt = BanamexParser().parse(_doc("05-ENE-2024 STARBUCKS REFORMA 120.00"))
    assert stmt.transactions[0].amount == Decimal("120.00")


def test_the_disclaimer_is_not_part_of_the_movement():
    """"(DATO NO VERIFICADO POR ESTA INSTITUCION)" is the bank talking, not the
    movement. Left in, its "verific-ado" matched the short label "ado" and
    filed a transfer to the user's own account under Transporte."""
    (spei,) = [t for t in _parse().transactions if "INTERBANCARIO" in t.raw_description]
    assert "VERIFICADO" not in spei.raw_description
    assert "FULANA,DE TAL/PEREZ" in spei.raw_description


def test_a_payment_to_a_banamex_card_is_a_self_transfer():
    from carguito.domain.services.flags import is_transfer

    assert is_transfer("PAGO DE SERVICIO 161770 A TB")
    # ...and an ordinary service payment is not.
    assert not is_transfer("PAGO DE SERVICIO CFE 123456")
