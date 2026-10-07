from datetime import date
from decimal import Decimal

from carguito.adapters.outbound.extraction.classifier import (
    KeywordTemplateClassifier,
    TEMPLATE_BANAMEX,
    TEMPLATE_BANCO_AZTECA,
    TEMPLATE_SAT_CFDI,
)
from carguito.adapters.outbound.parsing import (
    BanamexParser,
    GenericBankParser,
    SatCfdiParser,
)
from carguito.adapters.outbound.parsing.banco_azteca import BancoAztecaParser
from carguito.application.dtos.extraction import ExtractedDocument
from carguito.domain.value_objects.enums import SourceType, TxType


def _text_doc(lines: list[str]) -> ExtractedDocument:
    return ExtractedDocument(
        kind="text", filename="s.pdf", text="\n".join(lines), lines=lines
    )


def test_generic_bank_parser_extracts_transactions():
    lines = [
        "Estado de cuenta 2024",
        "05/01/2024 OXXO SAN RAFAEL 45.50",
        "07/01/2024 SPEI RECIBIDO NOMINA 12,000.00",
        "10/01/2024 NETFLIX.COM 299.00",
        "no date here 100.00",
    ]
    stmt = GenericBankParser().parse(_text_doc(lines))
    assert stmt.source_type == SourceType.BANK_PDF
    assert len(stmt.transactions) == 3
    oxxo = stmt.transactions[0]
    assert oxxo.tx_date == date(2024, 1, 5)
    assert oxxo.amount == Decimal("45.50")
    assert oxxo.tx_type == TxType.EXPENSE
    nomina = stmt.transactions[1]
    assert nomina.tx_type == TxType.INCOME
    assert nomina.amount == Decimal("12000.00")
    assert stmt.period_start == date(2024, 1, 5)
    assert stmt.period_end == date(2024, 1, 10)


def test_banamex_parser_tags_bank():
    lines = ["05-ENE-2024 STARBUCKS REFORMA 120.00"]
    stmt = BanamexParser().parse(_text_doc(lines))
    assert stmt.bank == "Banamex"
    assert stmt.transactions[0].tx_date == date(2024, 1, 5)
    assert stmt.transactions[0].amount == Decimal("120.00")


def test_sat_cfdi_parser():
    xml = (
        '<?xml version="1.0"?>'
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        'Total="1160.00" Fecha="2024-03-15T10:00:00" TipoDeComprobante="I">'
        '<cfdi:Emisor Nombre="TIENDAS SORIANA" Rfc="SOR123456"/>'
        "</cfdi:Comprobante>"
    )
    doc = ExtractedDocument(kind="xml", filename="factura.xml", xml=xml)
    stmt = SatCfdiParser().parse(doc)
    assert stmt.source_type == SourceType.SAT_XML
    assert len(stmt.transactions) == 1
    tx = stmt.transactions[0]
    assert tx.amount == Decimal("1160.00")
    assert tx.tx_date == date(2024, 3, 15)
    assert tx.raw_description == "TIENDAS SORIANA"
    assert tx.tx_type == TxType.EXPENSE


def test_classifier_routes_templates():
    clf = KeywordTemplateClassifier()
    banamex_doc = _text_doc(["CITIBANAMEX estado de cuenta", "05/01/2024 OXXO 45.50"])
    assert clf.classify(banamex_doc) == TEMPLATE_BANAMEX
    assert clf.detect_bank(banamex_doc) == "Banamex"
    cfdi_doc = ExtractedDocument(
        kind="xml", filename="f.xml", xml="<cfdi:Comprobante/>"
    )
    assert clf.classify(cfdi_doc) == TEMPLATE_SAT_CFDI


def test_one_counterparty_mention_does_not_claim_the_document():
    """The reported bug: a Nubank statement with transfers touching other
    banks classified as Banamex because 'banamex' appeared once in the body."""
    clf = KeywordTemplateClassifier()
    nu_doc = _text_doc(
        [
            "Nu México Financiera",
            "Estado de cuenta",
            *[f"0{d}/07/2026 Retiro de Cajita: Mis domingos 150.00" for d in range(1, 6)],
            "15/07/2026 SPEI enviado Banamex EDUARDO 500.00",
            "16/07/2026 EDUARDO B AZTECA Transferencia 300.00",
        ]
    )
    # No dedicated Nu parser, so the template is generic — but the bank is Nu,
    # and one Banamex counterparty line changes neither answer.
    assert clf.classify(nu_doc) == "generic_bank"
    assert clf.detect_bank(nu_doc) == "Nu"


def test_counterparty_spam_in_body_does_not_outvote_the_header():
    """Twenty transfers to Banco Azteca accounts are still Nu's statement."""
    clf = KeywordTemplateClassifier()
    doc = _text_doc(
        [
            "Nubank estado de cuenta",
            *[f"{d:02d}/07/2026 transferencia banco azteca 100.00" for d in range(1, 21)],
        ]
    )
    assert clf.detect_bank(doc) == "Nu"


def test_accents_do_not_hide_the_issuer():
    """The real Nu masthead says "Nu México" — with the accent. The old
    classifier lowercased without folding and never matched "nu mexico"."""
    clf = KeywordTemplateClassifier()
    doc = _text_doc(
        [
            "Nu México Financiera, S.A. de C.V.",
            "01/07/2026 Retiro de Cajita: Mis domingos 150.00",
        ]
    )
    assert clf.detect_bank(doc) == "Nu"
    assert clf.classify(doc) == "generic_bank"


def test_spei_receiving_bank_in_prose_does_not_claim_a_nu_statement():
    """The reported regression: Nu statements print the RECEIVING bank's
    formal name in prose SPEI blocks ("Banco receptor: Banco Nacional de
    México"). Product vocabulary — a Cajita movement — outweighs it: only
    the issuer's own products appear on its statement."""
    clf = KeywordTemplateClassifier()
    doc = _text_doc(
        [
            "Estado de cuenta",  # masthead is an image; no bank name in text
            "05/07/2026 Retiro de Cajita: Mis domingos 150.00",
            "12/07/2026 SPEI enviado 500.00",
            "Banco receptor: Banco Nacional de México",
            "18/07/2026 EDUARDO B AZTECA Transferencia 300.00",
        ]
    )
    assert clf.detect_bank(doc) == "Nu"
    assert clf.classify(doc) == "generic_bank"


def test_unknown_bank_stays_unnamed_and_generic():
    clf = KeywordTemplateClassifier()
    doc = _text_doc(["Caja Popular Los Pinos", "01/07/2026 abono 100.00"])
    assert clf.classify(doc) == "generic_bank"
    assert clf.detect_bank(doc) is None


# --------------------------------------------------------------------------- #
# Banco Azteca                                                                #
# --------------------------------------------------------------------------- #

#: A trimmed Banco Azteca statement, keeping the shapes that matter: the amount
#: on the line *after* the date, on the line *before* it, and merged into it.
#: Taken from a real 8-page statement whose totals are reproduced below.
_AZTECA_LINES = [
    "Banco Azteca S. A. Institución de Banca Múltiple",
    "Saldo Inicial al 11 de febrero 2026 = $6.59",
    "( + ) Depósitos del Periodo + $1,442.00",
    "( - ) Retiros del Periodo - $576.00",
    "Fecha Concepto Monto de la Operación",
    # amount BEFORE the date line
    "(+) $700.00 SPEI",
    "11/02/2026 TRANSFERENCIA SPEI A SU FAVOR",
    "EMISOR: NU MEXICO",
    "CUENTA: 638180010129397879",
    # amount AFTER the date line
    "13/02/2026 TRANSFERENCIA SPEI A SU FAVOR",
    "(+) $500.00 SPEI",
    "EMISOR: NU MEXICO",
    # amount merged INTO the date line
    "22/02/2026 TRANSFERENCIA SPEI A SU FAVOR (+) $242.00 SPEI",
    "25/02/2026 Retiro en ATM con celular (-) $500.00 BANCO AZTECA",
    "01/03/2026 COMPRA GAS TLALMANALCO 2",
    "(-) $76.00 COMPRA CON",
    # a date that is not a movement: no amount anywhere near it
    "10/03/2026 Saldo Final",
    "Banco Azteca, S.A., Institución de Banca Múltiple recibe las consultas",
]


def test_banco_azteca_parser_pairs_amounts_on_either_side_of_the_date():
    """generic_bank only sees the merged lines; this parser must find all five."""
    result = BancoAztecaParser().parse(_text_doc(_AZTECA_LINES))

    assert result.bank == "Banco Azteca"
    assert result.source_type == SourceType.BANK_PDF
    assert len(result.transactions) == 5

    by_date = {tx.tx_date: tx for tx in result.transactions}
    # Amount on the preceding line.
    assert by_date[date(2026, 2, 11)].amount == Decimal("700.00")
    assert by_date[date(2026, 2, 11)].raw_description == "TRANSFERENCIA SPEI A SU FAVOR"
    # Amount on the following line.
    assert by_date[date(2026, 2, 13)].amount == Decimal("500.00")
    # Amount merged into the date line, with the channel kept out of the concept.
    assert by_date[date(2026, 2, 22)].amount == Decimal("242.00")
    assert by_date[date(2026, 2, 22)].raw_description == "TRANSFERENCIA SPEI A SU FAVOR"


def test_banco_azteca_reads_direction_from_the_statements_own_marker():
    """(+)/(-) is a fact about the line and must beat any wording heuristic."""
    result = BancoAztecaParser().parse(_text_doc(_AZTECA_LINES))
    by_date = {tx.tx_date: tx for tx in result.transactions}

    assert by_date[date(2026, 2, 11)].tx_type is TxType.INCOME
    assert by_date[date(2026, 2, 25)].tx_type is TxType.EXPENSE
    # "COMPRA GAS" reads like an expense and is marked as one; the marker agrees.
    assert by_date[date(2026, 3, 1)].tx_type is TxType.EXPENSE

    income = sum(t.amount for t in result.transactions if t.tx_type is TxType.INCOME)
    expense = sum(t.amount for t in result.transactions if t.tx_type is TxType.EXPENSE)
    # The totals the statement itself declares, to the cent.
    assert income == Decimal("1442.00")
    assert expense == Decimal("576.00")


def test_banco_azteca_ignores_a_date_with_no_amount():
    """"10/03/2026 Saldo Final" is a cut-off date, not a movement."""
    result = BancoAztecaParser().parse(_text_doc(_AZTECA_LINES))
    assert date(2026, 3, 10) not in {tx.tx_date for tx in result.transactions}
    assert result.period_end == date(2026, 3, 1)


def test_azteca_statement_is_not_claimed_by_the_spei_counterparty():
    """EMISOR: NU MEXICO under every credit must not outvote the masthead."""
    classifier = KeywordTemplateClassifier()
    doc = _text_doc(_AZTECA_LINES)

    assert classifier.detect_bank(doc) == "Banco Azteca"
    assert classifier.classify(doc) == TEMPLATE_BANCO_AZTECA
