"""The price book: what the user's own tickets know about what things cost.

Every number this feature shows is a price the user paid, so these tests are
about arithmetic and about honesty in equal measure — the median and the spread
have to be right, and the *basis* has to be right, because "$18 vs $32" is a
lie when one of them was three times the size.

The chat half is tested for what it refuses. It has no internet, and the one
failure mode that would matter is a confident invented price, so the brief is
asserted on directly: if a store name or an absence is missing from it, the
model was never given the chance to answer correctly.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from carguito.domain.entities import Receipt, ReceiptItem
from carguito.domain.services.prices import build_price_book, find_product
from carguito.domain.services.products import product_key

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


def _receipt(store: str, day: int, items: list[tuple[str, str, str | None]]) -> Receipt:
    """A stored receipt: (description, amount, quantity) per line."""
    receipt = Receipt(
        user_id=DEV_USER,
        store=store,
        purchased_at=date(2026, 8, day),
        total=Decimal(sum(Decimal(a) for _, a, _ in items)),
        content_sha256=f"{day:064x}",
    )
    receipt.items = [
        ReceiptItem(
            user_id=DEV_USER,
            receipt_id=receipt.id,
            line_no=n,
            raw_text=description,
            description=description,
            product_key=product_key(description),
            amount=Decimal(amount),
            quantity=Decimal(quantity) if quantity else None,
            size=_size(description)[0],
            size_unit=_size(description)[1],
        )
        for n, (description, amount, quantity) in enumerate(items)
    ]
    return receipt


def _size(description: str):
    from carguito.domain.services.products import parse_size

    return parse_size(description)


# --- the arithmetic ------------------------------------------------------
def test_the_same_product_across_stores_is_one_history():
    book = build_price_book(
        [
            _receipt("Soriana", 12, [("LECHE LALA ENT 1L", "28.50", None)]),
            _receipt("Bodega Aurrera", 18, [("LECHE LALA ENTERA 1 LT", "29.90", None)]),
            _receipt("Oxxo", 22, [("LECHE LALA ENT 1L", "34.00", None)]),
        ]
    )
    assert len(book) == 1
    leche = book[0]
    assert leche.times_bought == 3
    assert leche.median == Decimal("29.90")
    assert leche.cheapest.store == "Soriana"
    assert leche.dearest.store == "Oxxo"
    # The most recent purchase is the one to act on, and it was the dear one.
    assert leche.latest.store == "Oxxo"
    assert leche.spread == Decimal("19.3")
    assert leche.latest_vs_median == Decimal("13.7")
    assert leche.stores == ("Oxxo", "Bodega Aurrera", "Soriana")


def test_different_sizes_are_compared_per_litre_and_say_so():
    book = build_price_book(
        [
            _receipt("Soriana", 12, [("COCA COLA 600ML", "18.00", None)]),
            _receipt("Chedraui", 20, [("COCA COLA 2L", "38.00", None)]),
        ]
    )
    coca = book[0]
    assert coca.basis == "unit"
    # 18.00 / 0.6 = 30.00 per litre against 38.00 / 2 = 19.00.
    assert coca.cheapest.store == "Chedraui"
    assert coca.median == Decimal("24.50")


def test_a_size_only_one_of_them_printed_falls_back_to_per_piece():
    """Half a basis is not a basis: it would compare a subset against itself."""
    book = build_price_book(
        [
            _receipt("Soriana", 12, [("COCA COLA 600ML", "18.00", None)]),
            _receipt("Oxxo", 20, [("COCA COLA", "22.00", None)]),
        ]
    )
    assert book[0].basis == "each"
    assert book[0].cheapest.store == "Soriana"


def test_a_product_bought_once_has_a_price_and_no_comparison():
    book = build_price_book([_receipt("Soriana", 12, [("PAN BIMBO GRANDE", "45.90", None)])])
    pan = book[0]
    assert pan.median == Decimal("45.90")
    assert pan.spread is None
    assert pan.latest_vs_median == Decimal("0.0")


def test_a_quantity_divides_into_a_unit_price():
    book = build_price_book([_receipt("Soriana", 12, [("BOLILLO", "24.00", "6")])])
    assert book[0].median == Decimal("4.00")


def test_undated_purchases_never_pass_for_the_most_recent():
    dated = _receipt("Soriana", 22, [("LECHE LALA ENT 1L", "34.00", None)])
    undated = _receipt("Oxxo", 12, [("LECHE LALA ENT 1L", "28.50", None)])
    object.__setattr__(undated, "purchased_at", None)
    assert build_price_book([undated, dated])[0].latest.store == "Soriana"


def test_search_matches_every_word():
    book = build_price_book(
        [
            _receipt("Soriana", 12, [("LECHE LALA ENT 1L", "28.50", None)]),
            _receipt("Soriana", 12, [("LECHE ALPURA DESLAC 1L", "31.00", None)]),
        ]
    )
    assert len(find_product(book, "leche")) == 2
    assert [p.name for p in find_product(book, "leche lala")] == ["Leche Lala Ent 1L"]
    assert find_product(book, "aguacate") == []


# --- over HTTP -----------------------------------------------------------
@pytest.fixture
def stocked(app):
    container = app.extensions["container"]
    for receipt in (
        _receipt("Soriana", 12, [("LECHE LALA ENT 1L", "28.50", None)]),
        _receipt("Oxxo", 22, [("LECHE LALA ENT 1L", "34.00", None), ("PAN BIMBO", "45.90", None)]),
    ):
        container.receipts.add(receipt)
    return container


def test_the_book_lists_summaries_without_every_purchase(client, stocked):
    body = client.get("/api/prices").get_json()
    assert body["total"] == 2
    leche = next(p for p in body["items"] if p["product_key"] == "leche lala entera")
    assert leche["times_bought"] == 2
    assert leche["median"] == 31.25
    assert leche["cheapest"]["store"] == "Soriana"
    # The list view is a list: the purchases behind each row are a click away.
    assert "points" not in leche


def test_one_product_comes_back_with_every_purchase(client, stocked):
    body = client.get("/api/prices/product?key=leche lala entera").get_json()
    assert [p["store"] for p in body["points"]] == ["Oxxo", "Soriana"]
    assert body["points"][0]["value"] == 34.00


def test_a_product_not_in_the_tickets_is_a_404_not_an_empty_answer(client, stocked):
    assert client.get("/api/prices/product?key=aguacate").status_code == 404


def test_search_narrows_the_book(client, stocked):
    body = client.get("/api/prices?q=pan").get_json()
    assert [p["name"] for p in body["items"]] == ["Pan Bimbo"]


# --- the chat ------------------------------------------------------------
def test_without_a_model_the_panel_is_disabled_not_broken(client):
    status = client.get("/api/prices/chat/status").get_json()
    # `reference` is empty too: the suite runs with the external source off.
    assert status == {"available": False, "model": "", "reference": ""}
    resp = client.post("/api/prices/chat", json={"question": "¿dónde está más barata la leche?"})
    assert resp.status_code == 503
    assert resp.get_json()["available"] is False


def test_the_brief_carries_stores_dates_and_the_comparison_basis(app, stocked):
    answerer = app.extensions["container"].answer_price_question
    brief = answerer.build_brief(user_id=DEV_USER, question="¿dónde está más barata la leche?")
    assert "Soriana" in brief and "Oxxo" in brief
    assert "por pieza" in brief
    assert "2026-08-22" in brief
    # The asked-about product gets its purchases listed one by one.
    assert brief.count("Leche Lala Ent 1L") >= 2
    # ...and the one that was not asked about does not.
    assert "DETALLE" in brief


def test_the_brief_says_out_loud_when_there_is_nothing_to_compare(app):
    answerer = app.extensions["container"].answer_price_question
    brief = answerer.build_brief(user_id=uuid4(), question="¿y la leche?")
    assert "SIN TICKETS" in brief


# --- the brief of one ticket ---------------------------------------------
def test_a_ticket_scoped_brief_is_the_basket_not_the_book(app, stocked):
    """A question asked from inside a ticket is about that ticket.

    The Soriana basket has one line. If the whole book leaked in, the Oxxo
    bread would be in the brief too — and the model would happily answer "lo
    más caro fue el pan" about a trip where no bread was bought.
    """
    container = app.extensions["container"]
    answerer = container.answer_price_question
    soriana = next(r for r in container.receipts.all_for_user(DEV_USER) if r.store == "Soriana")

    brief = answerer.build_brief(
        user_id=DEV_USER, question="¿qué me salió más caro?", receipt_id=soriana.id
    )
    assert "ESTE TICKET" in brief
    assert "Soriana" in brief and "2026-08-12" in brief
    assert "PAN BIMBO" not in brief and "Pan Bimbo" not in brief


def test_a_ticket_brief_still_carries_the_history_of_its_own_products(app, stocked):
    """Scoped, not blinkered: "¿pagué de más?" has to stay answerable."""
    container = app.extensions["container"]
    answerer = container.answer_price_question
    soriana = next(r for r in container.receipts.all_for_user(DEV_USER) if r.store == "Soriana")

    brief = answerer.build_brief(
        user_id=DEV_USER, question="¿pagué de más?", receipt_id=soriana.id
    )
    # The milk was also bought at the Oxxo, so its history comes along —
    # the *product's* history, not the other basket.
    assert "ESTOS PRODUCTOS EN TUS OTROS TICKETS" in brief
    assert "Oxxo" in brief


def test_a_ticket_whose_products_are_unique_says_there_is_no_comparison(app):
    container = app.extensions["container"]
    only = _receipt("Chedraui", 3, [("AGUACATE HASS", "17.88", None)])
    container.receipts.add(only)

    brief = container.answer_price_question.build_brief(
        user_id=DEV_USER, question="¿está caro?", receipt_id=only.id
    )
    assert "SIN HISTORIAL" in brief


def test_a_ticket_that_is_not_yours_is_not_read(app, stocked):
    """The repository read is user-scoped, so a guessed id says "no encontrado"."""
    container = app.extensions["container"]
    soriana = next(r for r in container.receipts.all_for_user(DEV_USER) if r.store == "Soriana")

    brief = container.answer_price_question.build_brief(
        user_id=uuid4(), question="¿qué compré?", receipt_id=soriana.id
    )
    assert "TICKET NO ENCONTRADO" in brief
    assert "Soriana" not in brief


def test_a_malformed_receipt_id_is_a_400(client, stocked):
    resp = client.post(
        "/api/prices/chat", json={"question": "¿qué compré?", "receipt_id": "no-soy-un-uuid"}
    )
    assert resp.status_code == 400


# --- external reference prices -------------------------------------------
def test_nothing_attached_means_no_lookup_at_all(app, stocked):
    """A general question never pays two seconds of somebody else's API,
    whatever words it happens to contain."""
    reference = _FakeReference([_quote()])
    answerer = _answerer(app, reference)
    assert answerer.reference_terms(user_id=DEV_USER, product_keys=[]) == []
    assert reference.asked is None


def test_an_attached_line_looks_up_its_stored_association(app, stocked):
    """The user points at `LECHE LALA ENT 1L`; the stored term says "leche"."""
    container = app.extensions["container"]
    container.product_reference_terms.upsert(DEV_USER, "leche lala entera", "leche", "user")
    answerer = _answerer(app, _FakeReference())
    assert answerer.reference_terms(
        user_id=DEV_USER, product_keys=["leche lala entera"]
    ) == ["leche"]


def test_a_key_that_is_not_the_users_is_ignored(app, stocked):
    answerer = _answerer(app, _FakeReference())
    assert answerer.reference_terms(user_id=DEV_USER, product_keys=["caviar"]) == []


def test_attached_products_get_the_detailed_brief_whatever_the_wording(app, stocked):
    answerer = _answerer(app, _FakeReference())
    brief = answerer.build_brief(
        user_id=DEV_USER, question="¿y esto?", product_keys=["leche lala entera"]
    )
    assert "DETALLE" in brief and brief.count("Leche Lala Ent 1L") >= 2


def test_malformed_product_keys_are_a_400(client):
    resp = client.post("/api/prices/chat", json={"question": "hola", "product_keys": "leche"})
    assert resp.status_code == 400



class _FakeReference:
    """A reference source that never touches the network.

    Records what it was asked for, which is half of what these tests check: the
    *decision to look something up* is as much a behaviour as what comes back.
    """

    def __init__(self, quotes=()):
        self.quotes = list(quotes)
        self.asked: list[str] | None = None

    @property
    def available(self) -> bool:
        return True

    @property
    def source_label(self) -> str:
        return "Fuente de prueba"

    def lookup(self, terms, *, hint=""):
        self.asked = list(terms)
        self.hint = hint
        return self.quotes


def _quote(term="leche", kind="LECHE ULTRAPASTEURIZADA"):
    from carguito.application.ports.outbound.references import PriceQuote

    return PriceQuote(
        term=term,
        kind=kind,
        observations=7755,
        median=Decimal("32.50"),
        low=Decimal("24.00"),
        low_where="WAL-MART",
        low_label="LECHE ULTRAPASTEURIZADA, LALA. 1 L",
        high=Decimal("48.00"),
        high_where="SUPER ISSSTE",
        observed=date(2026, 8, 20),
        source="Fuente de prueba",
    )


def _answerer(app, reference):
    from carguito.application.use_cases.prices import AnswerPriceQuestion

    container = app.extensions["container"]
    return AnswerPriceQuestion(
        chat=container.chat,
        compare=container.compare_prices,
        references=reference,
        product_terms=container.resolve_product_terms,
    )


def test_terms_are_tried_in_order_and_stop_at_the_first_that_answers(app, stocked):
    """So the brand words behind a head noun cost nothing."""

    class _OnlyKnowsDetergent(_FakeReference):
        def lookup(self, terms, *, hint=""):
            self.asked = (self.asked or []) + list(terms)
            return [_quote(term="detergente")] if terms == ["detergente"] else []

    reference = _OnlyKnowsDetergent()
    answerer = _answerer(app, reference)
    quotes = answerer.reference_quotes(["detergente", "great", "value"])

    assert len(quotes) == 1
    # "great" and "value" were never asked: the first term answered.
    assert reference.asked == ["detergente"]


def test_reference_prices_are_fenced_off_in_their_own_section(app, stocked):
    """The one property that matters: which numbers are the user's, and which
    are somebody else's."""
    answerer = _answerer(app, _FakeReference([_quote()]))
    brief = answerer.build_brief(
        user_id=DEV_USER,
        question="¿está cara la leche?",
        quotes=answerer.reference_quotes(["leche"]),
    )

    own, _, external = brief.partition("PRECIOS DE REFERENCIA")
    assert external, "the section must exist"
    assert "NO son compras del usuario" in external
    # Every external line names who says so and when.
    assert "Fuente de prueba" in external and "2026-08-20" in external
    # The mixed-presentation caveat travels with them, or the model will read
    # the median as a like-for-like price.
    assert "presentaciones mezcladas" in external
    # ...and the user's own purchases stay above the fence, untouched.
    assert "Soriana" in own


def test_a_reference_that_returns_nothing_leaves_the_brief_alone(app, stocked):
    answerer = _answerer(app, _FakeReference([]))
    with_source = answerer.build_brief(
        user_id=DEV_USER, question="¿está cara la leche?", quotes=answerer.reference_quotes(["leche"])
    )
    without = answerer.build_brief(user_id=DEV_USER, question="¿está cara la leche?")
    assert with_source == without
    assert "PRECIOS DE REFERENCIA" not in with_source


def test_the_suite_makes_no_outbound_call_by_default(app):
    """The container ships the null source under test settings, so a run on a
    laptop with no network is green for the right reason."""
    assert app.extensions["container"].price_reference.available is False


# --- the association between a shorthand and the world's word -------------
def test_a_persons_answer_is_never_overwritten_by_a_proposal(app):
    """What makes correcting one worth the user's time."""
    terms = app.extensions["container"].product_reference_terms
    terms.upsert(DEV_USER, "gv dete", "detergente para ropa", "user")
    terms.upsert(DEV_USER, "gv dete", "jabon", "auto")

    stored = terms.get(DEV_USER, "gv dete")
    assert stored.term == "detergente para ropa"
    assert stored.source == "user"
    # A person may still change their own mind.
    terms.upsert(DEV_USER, "gv dete", "detergente", "user")
    assert terms.get(DEV_USER, "gv dete").term == "detergente"


def test_a_proposal_that_is_not_a_term_is_refused(app):
    """Rejects rather than repairs: a stored sentence would be sent to a price
    survey forever."""
    from carguito.application.use_cases.prices import _clean_term

    assert _clean_term("detergente") == "detergente"
    assert _clean_term("Detergente.") == "detergente"
    assert _clean_term("desconocido") is None
    assert _clean_term("DETERGENTE 7L") is None
    assert _clean_term("No estoy seguro, pero podría ser detergente") is None


class _Decisions:
    """A typed model that answers one Choice with a scripted value."""

    available = True
    model_label = "jev-test"

    def __init__(self, choice: str, confidence: float = 0.9) -> None:
        self._choice = choice
        self._confidence = confidence
        self.asked: list = []

    def evaluate(self, *, state, questions):
        from carguito.application.ports.outbound.decisions import ChoiceAnswer

        self.asked.append((state, questions))
        options = list(questions["term"].criteria)
        return {
            "term": ChoiceAnswer(
                choice=self._choice,
                probabilities={o: 1.0 if o == self._choice else 0.0 for o in options},
                confidence=self._confidence,
            )
        }


class _Writer:
    """A text model that always writes the same term, and counts being asked."""

    available = True
    model_label = "texto-test"

    def __init__(self, answer: str = "detergente") -> None:
        self._answer = answer
        self.calls = 0

    def stream(self, *, system, messages, options=None):
        self.calls += 1
        yield self._answer


def _resolver(app, decisions=None, chat=None):
    from carguito.application.use_cases.prices import ResolveProductTerms
    from carguito.application.ports.outbound.decisions import NullDecisions

    container = app.extensions["container"]
    return ResolveProductTerms(
        container.product_reference_terms, chat or _Writer(), decisions or NullDecisions()
    )


def test_a_confident_choice_is_stored_and_the_text_model_is_never_asked(app):
    """The typed model answers out of a closed set, so there is nothing to
    clean up afterwards and no second round trip to pay for."""
    decisions, writer = _Decisions("leche", confidence=0.95), _Writer()
    resolver = _resolver(app, decisions, writer)

    assert resolver.resolve(
        user_id=DEV_USER, product_key="leche lala ent", description="LECHE LALA ENT 1L"
    ) == "leche"

    assert writer.calls == 0
    stored = resolver.stored(user_id=DEV_USER, product_key="leche lala ent")
    assert (stored.term, stored.source) == ("leche", "auto")
    # The line itself is the state; the shape rules live in the option set.
    state, questions = decisions.asked[0]
    assert state == "LECHE LALA ENT 1L"
    assert "leche" in questions["term"].criteria


def test_declining_hands_the_line_to_the_text_model(app):
    """Both ways of declining mean the same thing here: this line is not one of
    the words we have, so ask the model that can invent one."""
    from carguito.application.use_cases.prices import UNKNOWN_TERM

    for decisions in (_Decisions(UNKNOWN_TERM, 0.99), _Decisions("jabon", 0.31)):
        writer = _Writer("detergente")
        resolver = _resolver(app, decisions, writer)
        key = f"gv dete {decisions._choice}"

        assert resolver.resolve(user_id=DEV_USER, product_key=key, description="GV DETE 7L") == (
            "detergente"
        )
        assert writer.calls == 1


def test_a_word_written_once_becomes_a_word_choosable_after(app):
    """How the vocabulary grows. The text model is asked about a product no seed
    covers; the next line of the same kind is a Choice, not a sentence."""
    from carguito.application.use_cases.prices import SEED_TERMS, UNKNOWN_TERM

    assert "michelada" not in SEED_TERMS
    writer = _Writer("michelada")
    _resolver(app, _Decisions(UNKNOWN_TERM), writer).resolve(
        user_id=DEV_USER, product_key="mich prep", description="MICH PREPARADA 473"
    )
    assert writer.calls == 1

    decisions = _Decisions("michelada", 0.88)
    later = _resolver(app, decisions, _Writer())
    assert later.resolve(
        user_id=DEV_USER, product_key="mich prep lata", description="MICHELADA LATA"
    ) == "michelada"
    assert "michelada" in decisions.asked[0][1]["term"].criteria


def test_the_vocabulary_puts_the_users_own_words_first_and_is_capped(app):
    """The cap has to cut somewhere, and a word this account already uses is
    worth more than one nobody here has needed."""
    from carguito.application.use_cases.prices import (
        MAX_TERM_OPTIONS,
        SEED_TERMS,
        UNKNOWN_TERM,
    )

    resolver = _resolver(app)
    for i in range(MAX_TERM_OPTIONS + 20):
        resolver.set(user_id=DEV_USER, product_key=f"p{i}", term=f"propio{i}")

    vocabulary = resolver._vocabulary(DEV_USER)
    assert len(vocabulary) == MAX_TERM_OPTIONS
    assert all(v.startswith("propio") for v in vocabulary)
    assert UNKNOWN_TERM not in vocabulary
    # And with room to spare, the seed is there too.
    fresh = _resolver(app)._vocabulary(uuid4())
    assert set(SEED_TERMS) <= set(fresh)


def test_without_a_model_nothing_is_proposed_and_the_user_can_still_say_it(app):
    """A clone with no key still gets the feature, by typing."""
    resolver = app.extensions["container"].resolve_product_terms
    assert (
        resolver.resolve(user_id=DEV_USER, product_key="gv dete", description="GV DETE 7L")
        is None
    )
    assert resolver.set(user_id=DEV_USER, product_key="gv dete", term="  Detergente ").term == (
        "detergente"
    )


def test_terms_round_trip_over_http(client):
    assert client.get("/api/prices/terms").get_json() == {"items": [], "total": 0}

    saved = client.put(
        "/api/prices/terms", json={"product_key": "gv dete", "term": "detergente"}
    ).get_json()
    assert saved == {"product_key": "gv dete", "term": "detergente", "source": "user"}

    listed = client.get("/api/prices/terms").get_json()
    assert listed["items"] == [
        {"product_key": "gv dete", "term": "detergente", "source": "user"}
    ]


def test_an_empty_term_is_a_400(client):
    resp = client.put("/api/prices/terms", json={"product_key": "gv dete", "term": "  "})
    assert resp.status_code == 400


def test_the_brief_names_the_attached_product_as_the_subject(app, stocked):
    """"¿Dónde conseguirlo más barato?" has no noun. The chip is the noun.

    Without this section the model asked "¿de qué producto hablas?" — the one
    question the chip had already answered.
    """
    container = app.extensions["container"]
    container.product_reference_terms.upsert(DEV_USER, "leche lala entera", "leche", "user")
    answerer = _answerer(app, _FakeReference([_quote()]))
    brief = answerer.build_brief(
        user_id=DEV_USER,
        question="¿Dónde conseguirlo más barato?",
        product_keys=["leche lala entera"],
        quotes=answerer.reference_quotes(["leche"]),
    )
    subject, _, rest = brief.partition("PRODUCTOS CON PRECIO")
    assert "PRODUCTOS SEÑALADOS" in subject
    assert "Leche Lala Ent 1L" in subject and "buscado en la referencia como «leche»" in subject
    # The reference section still follows, fenced off as before.
    assert "PRECIOS DE REFERENCIA" in rest


def test_the_reducer_keeps_per_litre_and_per_kilo_prices():
    """The bug behind "no puedo comparar por litro".

    Profeco had 1 007 liquid detergents with a printed size; a kind-level median
    threw the presentation away and the model — correctly — refused to convert
    a 500 g bag into litres. The comparable figure has to survive the reduction.
    """
    from carguito.adapters.outbound.references.profeco import _reduce

    rows = [
        {"tipo_producto": "DETERGENTE P/ROPA", "precio": 115, "cadena_comercial": "BODEGA AURRERA",
         "producto": "DETERGENTE P/ROPA, MAS OSCURA, BOTELLA 3 LT. LÍQUIDO", "fecha_observacion": "2026-08-20"},
        {"tipo_producto": "DETERGENTE P/ROPA", "precio": 120, "cadena_comercial": "BODEGA AURRERA",
         "producto": "DETERGENTE P/ROPA, MAS OSCURA, BOTELLA 3 LT. LÍQUIDO", "fecha_observacion": "2026-08-20"},
        {"tipo_producto": "DETERGENTE P/ROPA", "precio": 18, "cadena_comercial": "CENTRAL DE ABASTOS",
         "producto": "DETERGENTE P/ROPA, BLANCA NIEVES, BOLSA 500 GR. POLVO", "fecha_observacion": "2026-08-20"},
    ] + [
        {"tipo_producto": "DETERGENTE P/ROPA", "precio": 24, "cadena_comercial": "X",
         "producto": "DETERGENTE P/ROPA, MAESTRO LIMPIO, BOLSA 1 KG. POLVO", "fecha_observacion": "2026-08-20"}
    ] * 3
    (quote,) = _reduce("detergente", rows, "test")

    litres = [u for u in quote.per_unit if u.unit == "l"]
    kilos = [u for u in quote.per_unit if u.unit == "kg"]
    # One line per chain per base -- its cheapest per unit. Six Bodegas are one line.
    assert [(str(u.per_unit), str(u.price), u.where) for u in litres] == [("38.33", "115.00", "BODEGA AURRERA")]
    # 500 g at $18 is $36/kg (Central de Abastos) and dearer than X's 1 kg bag at $24 — ranked.
    assert [(str(u.per_unit), u.where) for u in kilos] == [("24.00", "X"), ("36.00", "CENTRAL DE ABASTOS")]


# --- web listings: search, extraction, validation ---------------------------
def test_only_store_pages_survive_the_search_filter():
    """A news article about a promotion two years ago is a real search result and
    a worthless price. The domain is the one signal that separates them without
    reading the page."""
    from carguito.adapters.outbound.references.brave import is_store

    assert is_store("https://despensa.bodegaaurrera.com.mx/ip/detergente-liquido-7-l/0075")
    assert is_store("https://super.walmart.com.mx/ip/algo/123")
    assert not is_store("https://www.radioformula.com.mx/estilodevida/Walmart-el-jabon-de-7-L-en-179")
    assert not is_store("https://www.promodescuentos.com/ofertas/detergente-great-value")
    # A look-alike host does not match by suffix.
    assert not is_store("https://walmart.com.mx.evil.example/ip/x")


def test_extracted_listings_are_validated_not_repaired():
    from carguito.adapters.outbound.references.web_listings import _to_units

    handed = {"https://despensa.bodegaaurrera.com.mx/ip/gv-7l/1"}
    rows = [
        # The good one: handed URL, size and unit parse, price is a price.
        {"url": "https://despensa.bodegaaurrera.com.mx/ip/gv-7l/1", "store": "Bodega Aurrera",
         "product": "Detergente líquido Great Value 7 L", "size": 7, "unit": "l", "price": "169.90",
         "promo": False, "membership": False, "online_only": True},
        # A URL the model wrote but was never handed: an invention, dropped.
        {"url": "https://www.walmart.com.mx/ip/otro/2", "store": "Walmart", "product": "X 7 L",
         "size": 7, "unit": "l", "price": 175},
        # No size: nothing to compare per litre with, dropped.
        {"url": "https://despensa.bodegaaurrera.com.mx/ip/gv-7l/1", "store": "Bodega Aurrera",
         "product": "Detergente", "size": None, "unit": "l", "price": 100},
        # A unit we do not compare by, dropped.
        {"url": "https://despensa.bodegaaurrera.com.mx/ip/gv-7l/1", "store": "Bodega Aurrera",
         "product": "Cápsulas 40", "size": 40, "unit": "caps", "price": 300},
    ]
    (unit,) = _to_units(rows, handed)
    assert (str(unit.per_unit), unit.unit, str(unit.price)) == ("24.27", "l", "169.90")
    assert unit.url == "https://despensa.bodegaaurrera.com.mx/ip/gv-7l/1"
    # Conditions travel as visible labels, and a listing always says it is
    # undated: the page was read today, which is all it can claim.
    assert "solo en línea" in unit.notes and "leído hoy, sin fecha de publicación" in unit.notes


def test_the_models_json_is_tolerated_only_as_json():
    from carguito.adapters.outbound.references.web_listings import parse_listings

    assert parse_listings('```json\n[{"url": "u"}]\n```') == [{"url": "u"}]
    assert parse_listings("[]") == []
    assert parse_listings("No encontré precios.") == []
    assert parse_listings('{"url": "u"}') == []  # an object is not the contract


def test_the_web_reference_reads_a_quote_out_of_search_plus_model(app):
    """End to end with both halves faked: a store hit goes to the model, the
    model's JSON comes back as a per-litre quote labelled as a listing."""
    from carguito.adapters.outbound.references.brave import SearchHit
    from carguito.adapters.outbound.references.web_listings import WebPriceReference

    class _Search:
        available = True

        def search(self, query, *, count=10):
            assert "detergente" in query
            return [SearchHit(url="https://despensa.bodegaaurrera.com.mx/ip/gv/1",
                              title="Detergente Great Value 7 L", snippet="$169.90")]

    class _Chat:
        available = True
        model_label = "fake"

        def stream(self, *, system, messages, options=None):
            yield ('[{"url": "https://despensa.bodegaaurrera.com.mx/ip/gv/1", "store": "Bodega Aurrera",'
                   ' "product": "Detergente Great Value 7 L", "size": 7, "unit": "l", "price": 169.9}]')

    (quote,) = WebPriceReference(_Search(), _Chat()).lookup(["detergente"])
    assert quote.source == "listados en línea (Brave)"
    assert quote.observed == date.today()
    assert str(quote.per_unit[0].per_unit) == "24.27"


def test_the_composite_answers_with_whatever_source_is_healthy():
    import time as _time

    from carguito.application.ports.outbound.references import CompositePriceReference

    class _Slow(_FakeReference):
        def lookup(self, terms, *, hint=""):
            _time.sleep(0.2)
            return [_quote(kind="LENTA")]

    class _Broken(_FakeReference):
        def lookup(self, terms, *, hint=""):
            raise RuntimeError("boom")

    class _Off(_FakeReference):
        available = False

    started = _time.monotonic()
    composite = CompositePriceReference([_Slow(), _Broken(), _Off(), _FakeReference([_quote(kind="RÁPIDA")])])
    kinds = sorted(q.kind for q in composite.lookup(["x"]))
    assert kinds == ["LENTA", "RÁPIDA"]
    # Parallel: the slow one did not stack on top of the others.
    assert _time.monotonic() - started < 0.6
    # Three sources were available (the off one is not listed); the broken
    # one still counts as a source, it just answered nothing this time.
    assert composite.source_label == " · ".join(["Fuente de prueba"] * 3)


def test_the_container_composes_profeco_and_web_only_when_configured(tmp_path):
    from carguito.config.container import Container
    from carguito.config.settings import Settings

    base = dict(database_url=f"sqlite:///{tmp_path/'t.db'}", cube_path=":memory:",
                ingest_key_path=str(tmp_path / "k.json"), run_migrations=False)
    none = Container(Settings(**base, price_reference_city="", listings_source=""))
    assert none.price_reference.available is False
    # Brave with a key but no model: the web source drops itself, Profeco stands alone.
    partial = Container(Settings(**base, listings_source="brave", brave_search_api_key="k",
                                 llm_api_key="", llm_model=""))
    assert partial.price_reference.source_label == "Profeco (Quién es Quién en los Precios)"
    brave = Container(Settings(**base, listings_source="brave", brave_search_api_key="k",
                               llm_base_url="http://x", llm_api_key="k", llm_model="m"))
    assert brave.price_reference.source_label.endswith(" · listados en línea (Brave)")
    # Opt-in: Amazon needs no key and no model.
    amazon = Container(Settings(**base, listings_source="amazon", llm_api_key="", llm_model=""))
    assert amazon.price_reference.source_label.endswith(" · listados en Amazon México")



def test_amazon_results_parse_into_per_litre_quotes_and_drop_what_they_cannot():
    from carguito.adapters.outbound.references.amazon import parse_results

    item = (
        '<div data-component-type="s-search-result" data-asin="{asin}">{ad}<h2 class="x">'
        '<a class="a-link-normal" href="/Nombre/dp/{asin}/ref=sr_1"><span>{title}</span></a></h2>'
        '<span class="a-price"><span class="a-price-whole">{whole}</span>'
        '<span class="a-price-fraction">{frac}</span></span></div>'
    )
    page = "".join([
        item.format(asin="B08X321NRL", ad="", title="Great Value Detergente líquido para ropa de color 7 l", whole="415", frac="52"),
        item.format(asin="B07MBHSHV5", ad='<span class="puis-label-popover">Patrocinado</span>', title="MAS Color Detergente Líquido, 6.64L", whole="234", frac="00"),
        item.format(asin="B01M0PVRDL", ad="", title="MAS Bebé Detergente Líquido, 1.83 litros (24 Cargas)", whole="97", frac="50"),
        item.format(asin="B0GZ74NYBB", ad="", title="Detergente Liquido Persil Alta Higi", whole="253", frac="01"),  # no size
        item.format(asin="B08X321NRL", ad="", title="Great Value 7 l (duplicado)", whole="1", frac="00"),  # same asin
        '<span class="s-pagination-strip"></span>',
    ])
    units = parse_results(page)
    by_asin = {u.url.rsplit("/", 1)[1]: u for u in units}
    assert set(by_asin) == {"B08X321NRL", "B07MBHSHV5", "B01M0PVRDL"}
    assert str(by_asin["B08X321NRL"].per_unit) == "59.36" and by_asin["B08X321NRL"].unit == "l"
    # "1.83 litros", spelled out, is a size too.
    assert str(by_asin["B01M0PVRDL"].size) == "1.83" and str(by_asin["B01M0PVRDL"].per_unit) == "53.28"
    assert "patrocinado" in by_asin["B07MBHSHV5"].notes
    assert "patrocinado" not in by_asin["B08X321NRL"].notes
    # Every quote says what it is: a marketplace price read today, with a link.
    assert all("marketplace: vendedores varios" in u.notes and u.url.startswith("https://www.amazon.com.mx/dp/") for u in units)


def test_a_robot_check_page_yields_nothing_not_an_error():
    from carguito.adapters.outbound.references.amazon import parse_results

    assert parse_results("<html><body>Escribe los caracteres que ves</body></html>") == []



def test_a_rendered_page_is_condensed_to_its_price_lines():
    from carguito.adapters.outbound.references.firecrawl import condense

    page = "\n".join([
        "# Menú", "Inicio", "Despensa", "",
        "## Detergente líquido Great Value para ropa de color 7 l",
        "$150.00", "Precio regular $199.00", "",
        "Envío gratis en pedidos mayores a $499", "Categorías", "Ayuda", "Contacto",
        "Otros vendedores desde $205.00",
    ])
    out = condense(page)
    # The price lines and their neighbours survive; lines two or more away from
    # any price -- the menu -- do not. ("Categorías" sits next to the shipping
    # threshold, which is a price too; that is the rule working, not a leak.)
    assert "$150.00" in out and "Precio regular $199.00" in out
    assert "Detergente líquido Great Value" in out
    assert "Inicio" not in out and "Despensa" not in out and "# Menú" not in out


def test_firecrawl_results_become_store_hits_with_condensed_text(monkeypatch):
    import json as _json

    from carguito.adapters.outbound.references import firecrawl as fc

    payload = {"success": True, "data": [
        {"url": "https://www.soriana.com/detergente-quality-day-7-l/1187.html",
         "title": "Detergente Líquido Quality Day 7 l",
         "markdown": "Inicio\nDetergente Líquido Quality Day Ropa Color 7 l\n$169.90\nAntes $179.90\nAyuda"},
        {"url": "https://www.radioformula.com.mx/nota", "title": "Nota",
         "markdown": "El detergente de 7 L en $179"},  # not a store, dropped even if rendered
    ]}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return _json.dumps(payload).encode()

    captured = {}
    def fake_urlopen(request, timeout):
        captured["body"] = _json.loads(request.data)
        return _Resp()
    monkeypatch.setattr(fc.urllib.request, "urlopen", fake_urlopen)

    hits = fc.FirecrawlSearch("k").search("detergente 7 l precio")
    assert [h.url for h in hits] == ["https://www.soriana.com/detergente-quality-day-7-l/1187.html"]
    assert "$169.90" in hits[0].snippet and "Inicio" not in hits[0].snippet
    # Credits are the budget: the query is pinned to store domains before it runs.
    assert "site:walmart.com.mx" in captured["body"]["query"]
    assert captured["body"]["scrapeOptions"]["formats"] == ["markdown"]


def test_the_container_wires_firecrawl_behind_a_key_and_a_model(tmp_path):
    from carguito.config.container import Container
    from carguito.config.settings import Settings

    base = dict(database_url=f"sqlite:///{tmp_path/'t.db'}", cube_path=":memory:",
                ingest_key_path=str(tmp_path / "k.json"), run_migrations=False)
    on = Container(Settings(**base, listings_source="firecrawl", firecrawl_api_key="fc-x",
                            llm_base_url="http://x", llm_api_key="k", llm_model="m"))
    assert on.price_reference.source_label.endswith(" · listados en línea (Firecrawl)")
    # No model: nothing to read the page with, so the source drops itself.
    off = Container(Settings(**base, listings_source="firecrawl", firecrawl_api_key="fc-x",
                             llm_api_key="", llm_model=""))
    assert off.price_reference.source_label == "Profeco (Quién es Quién en los Precios)"



def test_a_rate_limited_reader_hands_the_pages_to_the_fallback(monkeypatch):
    """The pages were paid for in credits; a second model is cheaper than a
    second render."""
    from carguito.adapters.outbound.references import web_listings as wl
    from carguito.adapters.outbound.references.brave import SearchHit
    from carguito.application.ports.outbound.chat import ChatUnavailable

    monkeypatch.setattr(wl.time, "sleep", lambda s: None)
    hit = SearchHit(url="https://www.soriana.com/x/1.html", title="Quality Day 7 l", snippet="$169.90")

    class _Search:
        available = True
        def search(self, q, *, count=5): return [hit]

    class _Limited:
        available = True; model_label = "primary"; calls = 0
        def stream(self, *, system, messages, options=None):
            _Limited.calls += 1
            raise ChatUnavailable("El proveedor respondió 429: Provider returned error")

    class _Fallback:
        available = True; model_label = "fallback"
        def stream(self, *, system, messages, options=None):
            yield '[{"url": "https://www.soriana.com/x/1.html", "store": "Soriana", "product": "Quality Day 7 l", "size": 7, "unit": "l", "price": 169.9}]'

    (quote,) = wl.WebPriceReference(_Search(), _Limited(), engine="Firecrawl", fallback=_Fallback()).lookup(["detergente"])
    assert _Limited.calls == 2  # once, and once more after the pause
    assert str(quote.per_unit[0].per_unit) == "24.27"



def test_the_attached_products_printed_size_narrows_the_web_search(app, stocked):
    """"detergente" finds category pages; "detergente 7 l" finds product pages,
    and only product pages carry a price."""
    reference = _FakeReference([_quote()])
    answerer = _answerer(app, reference)
    # The stocked milk printed "1L" on the ticket.
    answerer.reference_quotes(["leche"], user_id=DEV_USER, product_keys=["leche lala entera"])
    assert reference.hint == "1 l"
