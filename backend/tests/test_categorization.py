from carguito.domain.entities import Category, Merchant
from carguito.domain.services.categorization import CategorizationService, normalize


def test_normalize_strips_accents_and_noise():
    assert normalize("  CAFÉ  Münchën!! ") == "cafe munchen"
    assert normalize("OXXO #123-A") == "oxxo 123 a"


def _service():
    categories = [
        Category(name="Sin Categoria", categorization_labels=[]),
        Category(name="Entretenimiento", categorization_labels=["netflix", "spotify"]),
        Category(name="Comida", categorization_labels=["oxxo", "uber eats"]),
    ]
    merchants = [
        Merchant(name="Netflix", labels=["netflix", "netflix.com"]),
        Merchant(name="OXXO", labels=["oxxo"]),
    ]
    return CategorizationService(categories, merchants), categories, merchants


def test_classify_matches_category_and_merchant():
    svc, categories, merchants = _service()
    result = svc.classify("PAGO NETFLIX.COM 12345")
    entertainment = next(c for c in categories if c.name == "Entretenimiento")
    netflix = next(m for m in merchants if m.name == "Netflix")
    assert result.category_id == entertainment.id
    assert result.merchant_id == netflix.id


def test_classify_falls_back_to_sin_categoria():
    svc, categories, _ = _service()
    result = svc.classify("SOME UNKNOWN MERCHANT")
    fallback = next(c for c in categories if c.name == "Sin Categoria")
    assert result.category_id == fallback.id
    assert result.merchant_id is None


def test_short_label_is_a_word_not_a_substring():
    categories = [
        Category(name="Gas", categorization_labels=["gas"]),
        Category(name="Sin Categoria", categorization_labels=[]),
    ]
    svc = CategorizationService(categories, [])
    gas = next(c for c in categories if c.name == "Gas")
    none = next(c for c in categories if c.name == "Sin Categoria")
    assert svc.classify("GAS CAPRIGO TLALMANALCO").category_id == gas.id
    assert svc.classify("TELCEL RECARGAS FONYOU").category_id == none.id


def test_longest_label_wins():
    categories = [
        Category(name="A", categorization_labels=["uber"]),
        Category(name="B", categorization_labels=["uber eats"]),
    ]
    svc = CategorizationService(categories, [])
    result = svc.classify("compra uber eats centro")
    b = next(c for c in categories if c.name == "B")
    assert result.category_id == b.id



def test_payroll_wording_files_under_ingresos(app):
    container = app.extensions["container"]
    cats = {c.name: c.id for c in container.categories.get_all()}
    assert "Ingresos" in cats
    classifier = container.categorizer if hasattr(container, "categorizer") else None
    from carguito.domain.services.categorization import CategorizationService

    svc = CategorizationService(container.categories.get_all(), container.merchants.get_all())
    nomina = svc.classify(
        "PAGO RECIBIDO DE SIST TRANSF Y PAGOS POR ORDEN DE VECH SOLUCIONES EN TRANSPORTE "
        "Nomina 2Q Noviembre"
    )
    assert nomina.category_id == cats["Nómina"]
    # "abono nomina": the longer label wins over Transferencias' "abono".
    assert svc.classify("ABONO NOMINA QUINCENAL").category_id == cats["Nómina"]
    # A transfer from a person is not income by wording alone.
    assert svc.classify("PAGO RECIBIDO DE AZTECA POR ORDEN DE ALGUIEN").category_id == cats["Sin Categoria"]


def test_outflow_wording_files_under_gasto(app):
    container = app.extensions["container"]
    cats = {c.name: c.id for c in container.categories.get_all()}
    assert "Gasto" in cats
    from carguito.domain.services.categorization import CategorizationService

    svc = CategorizationService(container.categories.get_all(), container.merchants.get_all())
    # A send to a person: the longer label beats Transferencias' "transferencia".
    assert (
        svc.classify("TRANSFERENCIA SPEI PAGO A TERCEROS GASPAR LOPEZ").category_id
        == cats["Envíos a terceros"]
    )
    assert svc.classify("COMISION ANUALIDAD TARJETA").category_id == cats["Comisiones e intereses"]
    assert svc.classify("INTERESES ORDINARIOS").category_id == cats["Comisiones e intereses"]
    # A plain purchase line is not an egreso by wording alone.
    assert svc.classify("PAGO OXXO CENTRO").category_id == cats["Conveniencia"]
    assert svc.classify("PAGO NETFLIX.COM").category_id == cats["Streaming"]
    assert svc.classify("PAGO GASOLINA SHELL").category_id == cats["Gasolina"]
    assert svc.classify("CARGO TIENDA DESCONOCIDA").category_id == cats["Sin Categoria"]


def test_a_default_added_later_reaches_an_existing_database(app):
    """The seed is per-name: a populated database gains "Ingresos" without
    losing anything the user changed in the categories it already had."""
    from carguito.adapters.outbound.persistence.seed import seed_reference_data

    container = app.extensions["container"]
    before = {c.name: c for c in container.categories.get_all()}
    assert "Ingresos" in before  # bootstrap already ran the seed once
    # Run it again: nothing duplicates.
    seed_reference_data(container.categories, container.merchants)
    after = [c.name for c in container.categories.get_all()]
    assert sorted(after) == sorted(before)
    nomina = next(c for c in container.categories.get_all() if c.name == "Nómina")
    ingresos = next(c for c in container.categories.get_all() if c.name == "Ingresos")
    assert nomina.parent_id == ingresos.id


def test_seed_grows_children_on_a_flat_taxonomy():
    """An older database that only has the roots gains the leaves, and the
    matcher vocabulary moves onto them. Extra labels the user added on a
    parent stay on the parent."""
    from carguito.adapters.outbound.persistence.seed import seed_reference_data
    from carguito.domain.entities import Category, Merchant

    class _Cats:
        def __init__(self) -> None:
            self.rows = [
                Category(
                    name="Transporte",
                    color="#eab308",
                    icon="commute",
                    categorization_labels=["uber", "gasolina", "mi ruta"],
                ),
                Category(name="Sin Categoria", categorization_labels=[]),
            ]

        def get_all(self):
            return list(self.rows)

        def add_many(self, categories):
            self.rows.extend(categories)

        def save_many(self, categories):
            by_id = {c.id: i for i, c in enumerate(self.rows)}
            for c in categories:
                self.rows[by_id[c.id]] = c

    class _Merchants:
        def get_all(self):
            return [Merchant(name="Uber", labels=["uber"])]

        def add_many(self, merchants):
            pass

    cats = _Cats()
    seed_reference_data(cats, _Merchants())
    by_name = {c.name: c for c in cats.get_all()}
    assert by_name["Gasolina"].parent_id == by_name["Transporte"].id
    assert by_name["Apps"].parent_id == by_name["Transporte"].id
    assert "gasolina" in by_name["Gasolina"].categorization_labels
    assert "uber" in by_name["Apps"].categorization_labels
    assert "gasolina" not in by_name["Transporte"].categorization_labels
    assert "uber" not in by_name["Transporte"].categorization_labels
    assert "mi ruta" in by_name["Transporte"].categorization_labels
    # A second pass does not duplicate.
    before = len(cats.get_all())
    seed_reference_data(cats, _Merchants())
    assert len(cats.get_all()) == before
