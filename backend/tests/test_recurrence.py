from datetime import date
from decimal import Decimal
from uuid import uuid4

from carguito.domain.entities import Transaction
from carguito.domain.services.recurrence import RecurrenceService, known_utility_key, series_key
from carguito.domain.value_objects.enums import TxType


def _tx(day: date, desc: str, amount: str, tx_type: TxType = TxType.EXPENSE):
    return Transaction(
        user_id=uuid4(),
        tx_date=day,
        amount=Decimal(amount),
        raw_description=desc,
        tx_type=tx_type,
    )


def test_detects_monthly_subscription():
    txs = [
        _tx(date(2024, 1, 5), "Netflix", "299"),
        _tx(date(2024, 2, 5), "Netflix", "299"),
        _tx(date(2024, 3, 5), "Netflix", "299"),
        _tx(date(2024, 1, 9), "One off store", "50"),
    ]
    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    g = groups[0]
    assert g.label == "Netflix"
    assert g.frequency == "monthly"
    assert g.occurrences == 3
    assert g.typical_amount == Decimal("299.00")
    assert g.amount_stable is True
    assert g.monthly_equivalent > Decimal("280")
    assert g.next_expected == date(2024, 4, 4)  # last + 30 (median interval)


def test_date_prefixes_do_not_split_a_series():
    """The reported case, verbatim: only the leading date token differs."""
    assert series_key("07-may-2026 PAYPAL *CABLEYCOMUN OPM 150323DI1MX +") == series_key(
        "06-abr-2026 PAYPAL *CABLEYCOMUN OPM 150323DI1MX +"
    )
    # Numeric and ISO date shapes too.
    assert series_key("07/05/2026 NETFLIX") == series_key("06/04/2026 NETFLIX")
    assert series_key("2026-05-07 NETFLIX") == series_key("2026-04-06 NETFLIX")

    txs = [
        _tx(date(2026, 4, 6), "06-abr-2026 PAYPAL *CABLEYCOMUN OPM 150323DI1MX +", "389"),
        _tx(date(2026, 5, 7), "07-may-2026 PAYPAL *CABLEYCOMUN OPM 150323DI1MX +", "389"),
        _tx(date(2026, 6, 6), "06-jun-2026 PAYPAL *CABLEYCOMUN OPM 150323DI1MX +", "389"),
    ]
    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    assert groups[0].frequency == "monthly"


def test_month_names_survive_outside_date_shapes():
    """A merchant named MAYO must not lose its identity to the date strip."""
    assert "mayo" in series_key("MAYO SEGUROS SA DE CV")
    assert "diciembre" in series_key("RESTAURANTE DICIEMBRE")


def test_branch_numbers_collapse_into_one_series():
    """"OXXO SUC 4412" and "OXXO SUC 8891" are the same habit."""
    assert series_key("OXXO SUC 4412 MX") == series_key("OXXO SUC 8891 MX")
    txs = [
        _tx(date(2024, 1, 3), "GYM SUC 4412 MENSUALIDAD", "500"),
        _tx(date(2024, 2, 3), "GYM SUC 8891 MENSUALIDAD", "500"),
        _tx(date(2024, 3, 3), "GYM SUC 1001 MENSUALIDAD", "500"),
    ]
    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    assert groups[0].occurrences == 3


def test_two_occurrences_is_a_coincidence():
    txs = [
        _tx(date(2024, 1, 5), "Spotify", "129"),
        _tx(date(2024, 2, 5), "Spotify", "129"),
    ]
    assert RecurrenceService().detect(txs) == []


def test_irregular_visits_are_not_a_subscription():
    """A merchant you merely visit often has no rhythm."""
    txs = [
        _tx(date(2024, 1, 2), "Cafetería", "80"),
        _tx(date(2024, 1, 5), "Cafetería", "95"),
        _tx(date(2024, 2, 28), "Cafetería", "70"),
        _tx(date(2024, 3, 2), "Cafetería", "88"),
    ]
    assert RecurrenceService().detect(txs) == []


def test_variable_amount_recurs_but_is_flagged_unstable():
    """CFE varies charge to charge; it still recurs on a rhythm."""
    txs = [
        _tx(date(2024, 1, 10), "CFE RECIBO", "300"),
        _tx(date(2024, 2, 9), "CFE RECIBO", "520"),
        _tx(date(2024, 3, 11), "CFE RECIBO", "410"),
    ]
    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    assert groups[0].frequency == "monthly"
    assert groups[0].amount_stable is False


def test_named_dentist_every_six_weeks_is_bimonthly():
    """The reported case: four «Dentista» transfers ~6–7 weeks apart,
    plus one longer skip. Median 47 days sat in the monthly/bimonthly gap."""
    txs = []
    for day, amount in [
        (date(2026, 1, 25), "700"),
        (date(2026, 4, 19), "700"),
        (date(2026, 6, 5), "850"),
        (date(2026, 7, 19), "700"),
    ]:
        t = _tx(day, "xochitl flores fonseca Transferencia", amount)
        t.description = "Dentista"
        txs.append(t)
    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    g = groups[0]
    assert g.label == "Dentista"
    assert g.frequency == "bimonthly"
    assert g.occurrences == 4


def test_same_day_double_capture_does_not_hide_a_monthly_gym():
    """The reported case: GYMFUERZAFIT posted twice on 22-jun, and one
    skipped month. The 0-day gap used to fail regularity."""
    txs = []
    for day, amount, raw in [
        (date(2026, 2, 16), "760", "17-feb-2026 MERPAGO*GYMFUERZAFIT2 MAG 2105031W3MX +"),
        (date(2026, 3, 18), "800", "19-mar-2026 MERPAGO*GYMFUERZAFIT2 MAG 2105031W3MX +"),
        (date(2026, 6, 22), "800", "23-jun-2026 MERPAGO*GYMFUERZAFIT2 MAG 2105031W3MX +"),
        (date(2026, 6, 22), "800", "24-jun-2026 MERPAGO*GYMFUERZAFIT2 MAG 2105031W3 I6062418092"),
        (date(2026, 7, 22), "800", "23-jul-2026 MERPAGO*GYMFUERZAFIT2 MAG 2105031W3MX +"),
    ]:
        t = _tx(day, raw, amount)
        t.description = "GYM"
        txs.append(t)
    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    g = groups[0]
    assert g.label == "GYM"
    assert g.frequency == "monthly"
    assert g.occurrences == 4
    assert g.typical_amount == Decimal("800.00")


def test_cfe_product_lines_and_a_fee_are_one_bimonthly_bill():
    """CFE residential is bimestral; SUM SERV vs CONTIGO is the same utility,
    and a $18 CFE CONTIGO fee must not break the cadence."""
    assert known_utility_key("28-may-2026 CFE SUM SERV BAS CR MU CSS 160330CP7 +") == "cfe"
    assert known_utility_key("29-jul-2026 CFE CONTIGO MU CSS 160330CP7 +") == "cfe"

    txs = [
        _tx(date(2026, 3, 25), "26-mar-2026 CFE SUM SERV BAS CR MU CSS 160330CP7 +", "806"),
        _tx(date(2026, 5, 27), "28-may-2026 CFE SUM SERV BAS CR MU CSS 160330CP7 +", "2014"),
        _tx(date(2026, 7, 6), "07-jul-2026 CFE CONTIGO MU CSS 160330CP7 +", "18"),
        _tx(date(2026, 7, 28), "29-jul-2026 CFE CONTIGO MU CSS 160330CP7 +", "2021"),
    ]
    txs[-1].description = "Pago Luz"
    txs[-2].description = "Pago Luz"

    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    g = groups[0]
    assert g.key == "util:cfe"
    assert g.frequency == "bimonthly"
    assert g.occurrences == 3  # the $18 fee is not the bill
    assert g.label == "Pago Luz"


def test_semiannual_policy_is_a_bill_even_when_the_amount_moves():
    """A semestral policy is a payment, not a store visit. The amount may
    move (renewal vs adjustment) and the cadence is still the commitment."""
    txs = [
        _tx(date(2024, 1, 15), "SEGURO AUTOS GNP", "2100"),
        _tx(date(2024, 7, 15), "SEGURO AUTOS GNP", "4200"),
        _tx(date(2025, 1, 14), "SEGURO AUTOS GNP", "9000"),
    ]
    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    g = groups[0]
    assert g.frequency == "semiannual"
    assert g.amount_stable is False


def test_weekly_store_with_a_swinging_ticket_still_has_a_rhythm():
    """OXXO every week is a habit the detector can see. Pagos is what
    leaves it off the calendar: the amount is not stable and the cadence
    is not a bill cycle."""
    txs = [
        _tx(date(2024, 1, 2), "OXXO SUC 4412", "86"),
        _tx(date(2024, 1, 9), "OXXO SUC 8891", "214"),
        _tx(date(2024, 1, 16), "OXXO SUC 1001", "47"),
        _tx(date(2024, 1, 23), "OXXO SUC 2204", "163"),
    ]
    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    assert groups[0].frequency == "weekly"
    assert groups[0].amount_stable is False


def test_biweekly_cadence():
    txs = [
        _tx(date(2024, 1, 1), "Prestamo quincenal", "750"),
        _tx(date(2024, 1, 15), "Prestamo quincenal", "750"),
        _tx(date(2024, 1, 30), "Prestamo quincenal", "750"),
        _tx(date(2024, 2, 14), "Prestamo quincenal", "750"),
    ]
    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    assert groups[0].frequency == "biweekly"


def test_income_and_excluded_are_ignored():
    nomina = [
        _tx(date(2024, m, 1), "Nomina", "1000", TxType.INCOME) for m in (1, 2, 3)
    ]
    excluded = []
    for m in (1, 2, 3):
        t = _tx(date(2024, m, 5), "Transfer propio", "500")
        t.excluded_from_stats = True
        excluded.append(t)
    assert RecurrenceService().detect(nomina + excluded) == []


def test_taught_alias_merges_differently_worded_series():
    """Naming a charge and grouping its series are the same act."""
    txs = [
        _tx(date(2026, 3, 6), "06-mar-2026 PAYPAL *CABLEYCOMUN OPM 150323DI1MX +", "389"),
        _tx(date(2026, 4, 6), "06-abr-2026 CABLEYCOMUN SA CV MX 998812", "389"),
        _tx(date(2026, 5, 7), "07-may-2026 PAYPAL *CABLEYCOMUN OPM 441209XX2MX +", "389"),
    ]
    # Without the alias, the two wordings are different heuristic series —
    # neither reaches three occurrences, so nothing qualifies.
    assert RecurrenceService().detect(txs) == []

    # With the taught label, they are one series under the user's name.
    groups = RecurrenceService().detect(txs, aliases=[("cableycomun", "Cable e Internet")])
    assert len(groups) == 1
    g = groups[0]
    assert g.label == "Cable e Internet"
    assert g.key == "alias:cableycomun"
    assert g.occurrences == 3
    assert g.frequency == "monthly"


def test_shared_user_name_groups_spei_that_embed_the_month():
    """The reported case: each SPEI names the month, so the heuristic splits
    them; the user already named every row «Colegiatura Demian»."""
    months = [
        (date(2025, 12, 2), "DICIEMBRE"),
        (date(2026, 1, 7), "ENERO"),
        (date(2026, 2, 4), "FEBRERO"),
        (date(2026, 3, 2), "MARZO"),
        (date(2026, 4, 6), "ABRIL"),
        (date(2026, 5, 6), "MAYO"),
        (date(2026, 6, 3), "JUNIO"),
        (date(2026, 7, 9), "JULIO"),
    ]

    def spei(month: str) -> str:
        return (
            "PAGO INTERBANCARIO A BANORTE AL BENEF. JUANA DE ASBAJE "
            f"Y RAMIREZ DE SANTILLANA CLAVE 1 SECUNDARIA {month} MISMO DIA"
        )

    unnamed = [_tx(day, spei(month), "3700") for day, month in months]
    assert RecurrenceService().detect(unnamed) == []

    named = []
    for day, month in months:
        t = _tx(day, spei(month), "3700")
        t.description = "Colegiatura Demian"
        named.append(t)
    groups = RecurrenceService().detect(named)
    assert len(groups) == 1
    g = groups[0]
    assert g.label == "Colegiatura Demian"
    assert g.key == "named:colegiatura demian"
    assert g.occurrences == 8
    assert g.frequency == "monthly"


def test_shared_user_name_wins_over_a_generic_alias():
    """A taught label that is a SPEI substring must not hide the user's name."""
    months = [
        (date(2026, 1, 7), "ENERO"),
        (date(2026, 2, 4), "FEBRERO"),
        (date(2026, 3, 2), "MARZO"),
    ]
    txs = []
    for day, month in months:
        raw = f"PAGO INTERBANCARIO A BANORTE SECUNDARIA {month} MISMO DIA"
        t = _tx(day, raw, "3700")
        t.description = "Colegiatura Demian"
        txs.append(t)
    groups = RecurrenceService().detect(txs, aliases=[("pago", "Transferencias")])
    assert len(groups) == 1
    assert groups[0].label == "Colegiatura Demian"
    assert groups[0].key == "named:colegiatura demian"


def test_alias_changes_the_label_but_never_splits_the_series():
    """Identity is the raw text; display is the freshest description."""
    txs = [
        _tx(date(2024, 1, 5), "POCK*SUPERLECLERC MX", "400"),
        _tx(date(2024, 2, 5), "POCK*SUPERLECLERC MX", "400"),
        _tx(date(2024, 3, 5), "POCK*SUPERLECLERC MX", "400"),
    ]
    # Only the most recent row has been renamed so far (mid-transition).
    txs[-1].description = "Súper cerca de casa"
    groups = RecurrenceService().detect(txs)
    assert len(groups) == 1
    assert groups[0].occurrences == 3
    assert groups[0].label == "Súper cerca de casa"
