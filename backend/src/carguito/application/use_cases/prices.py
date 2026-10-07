"""Comparing what the user paid for the same thing, and answering about it.

Two halves, and — exactly like the workstation chat — the first is the one that
matters. The **price book** is computed from the user's own receipt lines by
``domain/services/prices.py``: every figure in it is a price they paid, at a
named store, on a date. The model never computes; it reads that book out loud
and answers the question that was asked of it.

The scope is deliberately narrow and is stated to the model three times: this
window knows what *your tickets* say. It cannot look up what a litre of milk
costs at the Walmart down the street, and inventing that number would be worse
than useless in a product whose entire posture is that a figure on screen can
be traced back to a document the user owns.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from uuid import UUID

from ...domain.entities import Receipt
from ...domain.services.prices import (
    ProductPrices,
    build_price_book,
    find_product,
    mentioned_in,
)
from ..ports.outbound import ReceiptRepository
from ..ports.outbound.chat import ChatMessage, ChatOptions, ChatPort
from ..ports.outbound.decisions import (
    Choice,
    ChoiceAnswer,
    DecisionPort,
    NullDecisions,
)
from ..ports.outbound.references import (
    NullPriceReference,
    PriceQuote,
    PriceReference,
    ProductTermRepository,
    ReferenceTerm,
)

logger = logging.getLogger(__name__)

#: How many products the brief describes in summary. Past this the list is a
#: pantry inventory, not context: the tail is bought once and has no comparison.
BRIEF_PRODUCTS = 60

#: How many products get their full purchase-by-purchase history, and how deep.
DETAILED_PRODUCTS = 6
DETAIL_POINTS = 12

#: How many search terms one question may send to the external reference. Each
#: is a round trip of a couple of seconds, and a question about more than two
#: products at once is not a question anybody asks.
REFERENCE_TERMS = 2

SYSTEM = """\
Eres el analista de precios de Tomin, una app de finanzas personales mexicana.

Respondes preguntas sobre lo que el usuario ha pagado por sus productos, según
los tickets que él mismo fotografió. Todo lo que sabes está en el resumen de
abajo.

Reglas, en orden de importancia:

1. NUNCA inventes un precio. Cada cifra que escribas debe estar en el resumen,
   o ser una operación aritmética simple sobre esas cifras, y si haces la
   operación, dila.
2. NO tienes acceso a internet. Tus únicas fuentes son (a) los tickets del
   usuario y (b) si el resumen trae PRECIOS DE REFERENCIA, esas observaciones
   de Profeco. Si te preguntan dónde está más barato y hay referencia, úsala:
   di la cadena más barata observada, el precio y la fecha, con la reserva de
   la regla 9. Si no hay referencia, di que solo puedes comparar sus tickets.
3. Si el resumen trae PRODUCTOS SEÑALADOS, la pregunta es sobre ESOS
   productos aunque la frase no los nombre («¿dónde conseguirlo más barato?»
   se refiere a ellos). Nunca pidas que te digan de qué producto hablan.
4. Si un producto no aparece en el resumen, dilo: «no lo veo en tus tickets».
   No lo confundas con uno parecido.
5. Un producto comprado una sola vez no tiene comparación. Di el precio y di
   que solo hay una compra.
6. Compara únicamente con la misma base que trae el resumen. Si dice «por
   litro», compara por litro; si dice «por pieza», no inventes el tamaño.
7. Habla en español de México, en segunda persona, directo y sin adornos. Sin
   emojis. Sin listas largas cuando basta un párrafo.
8. Cuando la diferencia sea pequeña (menos de 5%), dilo así: no vale la pena
   cambiar de tienda por eso.
9. Si el resumen trae una sección PRECIOS DE REFERENCIA, esos números NO son
   del usuario: son observaciones publicadas por un tercero. Cada vez que uses
   uno, di la fuente y la fecha, y di que es referencia. NUNCA los sumes ni los
   promedies junto a lo que el usuario pagó, y NUNCA presentes uno como si
   fuera una compra suya. La mediana y el mínimo del tipo mezclan tamaños y
   solo ubican un rango. Las líneas «por litro» / «por kilo» SÍ son
   comparables con el precio por litro o por kilo del usuario, siempre en la
   misma base (nunca litros contra kilos): úsalas para responder «¿cuál es
   más barato por litro?» nombrando presentación, precio y cadena.
   Hay dos clases de referencia y las distingues SIEMPRE en tu texto:
   «observado por Profeco el <fecha>» (alguien lo vio en un anaquel) y
   «listado en línea, leído hoy» (una página de tienda lo mostraba; incluye
   la URL). Si un listado trae nota (promoción, membresía, solo en línea),
   dila. Nunca promedies ni mezcles las dos clases entre sí.
10. Formato: Markdown ligero solamente — **negritas** para la cifra que
   responde, listas con guiones cuando enumeres compras. NUNCA uses LaTeX ni
   notación matemática: la pantalla no lo dibuja.

No repitas el resumen de vuelta. Responde la pregunta."""


#: What a model is asked, once per product, to turn a ticket's shorthand into
#: a word the outside world files it under. Deliberately tiny: one line in, one
#: or two words out, and an explicit way to say it does not know.
TERM_SYSTEM = """\
Traduces la linea abreviada de un ticket mexicano al nombre generico del
producto, tal como se buscaria en una encuesta de precios de gobierno.

Reglas:
1. Responde SOLO el nombre generico. Minusculas. Sin marca, sin tamano, sin
   presentacion. Una o dos palabras.
2. Ejemplos: "GV DETE 7L" -> detergente · "LECHE LALA ENT 1L" -> leche ·
   "ZOTE BARRA" -> jabon · "AGUACATE HAS" -> aguacate
3. Si no reconoces el producto, responde exactamente: desconocido

No expliques. No agregues nada."""

#: Longest answer worth trusting. Anything past this is prose, not a term.
MAX_TERM_WORDS = 2
MAX_TERM_CHARS = 40

#: What a typed decision may answer when none of the words fit. The same escape
#: hatch as rule 3 of TERM_SYSTEM, except here it is an option the model must
#: pick rather than a string it must spell.
UNKNOWN_TERM = "desconocido"

#: Below this, a Choice is the model saying it cannot tell the words apart, and
#: the decision is handed on rather than stored. Not 0.9: the stakes are one
#: query to a price survey, the screen shows the term it used, and an ``auto``
#: proposal can never overwrite a ``user`` correction. But above the floor where
#: a flat distribution means nothing was decided at all.
TERM_CONFIDENCE = 0.6

#: How many words one Choice may be asked over. The state and the questions
#: share a budget of roughly 32k tokens; a hundred short generics is nowhere
#: near it, and a list longer than this is a catalogue nobody curates.
MAX_TERM_OPTIONS = 140

#: The vocabulary a fresh account starts with: the generics a Mexican basket is
#: actually filed under in a price survey. It is a seed, not a ceiling -- the
#: user's own stored terms join it, so a word the text model proposes once is a
#: word the typed model can choose from ever after.
SEED_TERMS = (
    "aceite", "agua", "aguacate", "ajo", "arroz", "atun", "avena", "azucar",
    "bistec", "bolillo", "cafe", "caldo", "camaron", "carbon", "cebolla",
    "cereal", "cerveza", "chile", "chocolate", "cloro", "crema", "desodorante",
    "detergente", "durazno", "elote", "epazote", "frijol", "fruta", "galletas",
    "gelatina", "harina", "huevo", "jabon", "jamon", "jitomate", "jugo",
    "leche", "lechuga", "lenteja", "limon", "maiz", "mantequilla", "manzana",
    "margarina", "mayonesa", "melon", "mermelada", "miel", "mole", "mostaza",
    "naranja", "nopal", "nuez", "pan", "papa", "papel", "pasta", "pepino",
    "pescado", "pina", "platano", "pollo", "puerco", "queso", "refresco",
    "res", "sal", "salchicha", "salsa", "sardina", "servilletas", "shampoo",
    "sopa", "suavizante", "te", "tomate", "tortilla", "tostadas", "toalla",
    "tuna", "uva", "verdura", "vinagre", "yogurt", "zanahoria",
)

#: What the typed model is asked. The equivalent of TERM_SYSTEM, except the
#: rules about shape ("one or two words", "lowercase", "no brand") are gone:
#: the option set enforces them, which is the entire reason to ask this way.
TERM_INSTRUCTIONS = (
    "Esta es una linea abreviada de un ticket mexicano. "
    "Elige el nombre generico bajo el que ese producto se buscaria en una "
    f"encuesta de precios. Si ninguna opcion nombra el producto, elige "
    f"'{UNKNOWN_TERM}'."
)


class ResolveProductTerms:
    """What a ticket's shorthand is called out in the world.

    ``GV DETE 7L`` and ``detergente`` are not a normalisation apart -- no regex
    turns one into the other, because the relation is knowledge rather than
    spelling. So it is stored, once per product, and every later question about
    that line inherits it.

    A model proposes; a person decides. The repository refuses to let an
    ``auto`` proposal overwrite a ``user`` correction, which is what makes
    correcting one worth the user's time.

    Two models propose, in the order of what each is actually good at. The
    typed one **chooses** among words this account already uses plus a seed
    vocabulary, so its answer cannot be a sentence, a size or an apology -- the
    shape rules that :func:`_clean_term` exists to enforce are enforced by the
    option set instead. The text one is asked only about the lines the first
    could not place, which is how the vocabulary grows: a word written once
    becomes a word choosable ever after.

    Both are optional and in every combination. Neither configured is the
    normal state of a fresh clone: nothing is proposed, the screen says "sin
    asociar", and the user types the term themselves.
    """

    def __init__(
        self,
        terms: ProductTermRepository,
        chat: ChatPort,
        decisions: DecisionPort | None = None,
    ) -> None:
        self._terms = terms
        self._chat = chat
        self._decisions = decisions or NullDecisions()

    def all_for_user(self, *, user_id: UUID) -> list[ReferenceTerm]:
        return self._terms.all_for_user(user_id)

    def set(self, *, user_id: UUID, product_key: str, term: str) -> ReferenceTerm:
        cleaned = " ".join(term.strip().lower().split())
        if not cleaned:
            raise ValueError("El termino no puede estar vacio.")
        if len(cleaned) > MAX_TERM_CHARS:
            raise ValueError(f"El termino debe tener {MAX_TERM_CHARS} caracteres o menos.")
        self._terms.upsert(user_id, product_key, cleaned, "user")
        return ReferenceTerm(product_key=product_key, term=cleaned, source="user")

    def stored(self, *, user_id: UUID, product_key: str) -> ReferenceTerm | None:
        """The association as it stands. Never proposes one."""
        return self._terms.get(user_id, product_key)

    def resolve(self, *, user_id: UUID, product_key: str, description: str) -> str | None:
        """The stored term, or one learned now and stored. ``None`` if neither.

        ``None`` is a real answer and the screen shows it as "sin asociar": a
        product nobody could name is better left unsearched than searched for
        the wrong thing, which is the failure this whole table exists to end.
        """
        stored = self._terms.get(user_id, product_key)
        if stored:
            return stored.term
        proposed = self._propose(user_id, description or product_key)
        if not proposed:
            return None
        self._terms.upsert(user_id, product_key, proposed, "auto")
        return proposed

    def _propose(self, user_id: UUID, description: str) -> str | None:
        """The typed model first, the text model for what it could not place."""
        chosen = self._choose(user_id, description)
        if chosen:
            return chosen
        return self._write(description)

    def _choose(self, user_id: UUID, description: str) -> str | None:
        """One word out of a closed set, or nothing.

        Nothing covers both ways the model declines -- picking
        ``desconocido``, and picking something without enough confidence to
        act on -- because both mean the same thing here: this line is not one
        of the words we already have, so ask the model that can invent one.
        """
        if not self._decisions.available:
            return None
        vocabulary = self._vocabulary(user_id)
        if not vocabulary:
            return None
        criteria: dict[str, str | None] = dict.fromkeys(vocabulary, None)
        criteria[UNKNOWN_TERM] = "Ninguna de las otras opciones nombra este producto."
        try:
            answers = self._decisions.evaluate(
                state=description,
                questions={"term": Choice(instructions=TERM_INSTRUCTIONS, criteria=criteria)},
            )
        except Exception:  # pragma: no cover - a proposal is never load-bearing
            logger.warning("could not choose a reference term for %r", description)
            return None
        answer = answers.get("term")
        if not isinstance(answer, ChoiceAnswer):
            return None
        if answer.choice == UNKNOWN_TERM or answer.confidence < TERM_CONFIDENCE:
            logger.info(
                "term for %r left to the text model (%s at %.2f)",
                description, answer.choice, answer.confidence,
            )
            return None
        return answer.choice

    def _vocabulary(self, user_id: UUID) -> list[str]:
        """The words this Choice may answer with: the user's own, then the seed.

        The user's come first because the cap has to cut somewhere, and a word
        this account has already used is worth more than one nobody here has
        needed. Read fresh rather than cached: this runs only on a miss -- the
        same path that is about to write a row -- so the cost is one indexed
        read per *new* product, not per lookup, and a cache here would go stale
        the moment somebody corrected a term.
        """
        seen: dict[str, None] = {}
        for stored in self._terms.all_for_user(user_id):
            term = stored.term.strip().lower()
            if term and term != UNKNOWN_TERM:
                seen[term] = None
        for term in SEED_TERMS:
            seen.setdefault(term, None)
        return list(seen)[:MAX_TERM_OPTIONS]

    def _write(self, description: str) -> str | None:
        if not self._chat.available:
            return None
        try:
            answer = "".join(
                self._chat.stream(
                    system=TERM_SYSTEM,
                    messages=[ChatMessage(role="user", content=description)],
                    # Cold: the same line should map to the same word every time.
                    options=ChatOptions(temperature=0),
                )
            )
        except Exception:  # pragma: no cover - a proposal is never load-bearing
            logger.warning("could not propose a reference term for %r", description)
            return None
        return _clean_term(answer)


def _clean_term(answer: str) -> str | None:
    """A model's answer, or nothing.

    Rejects rather than repairs. A term is one or two plain words; anything
    else -- a sentence, a size, an apology -- means the model did not answer the
    question, and storing it would send that string to a price survey forever.
    """
    term = " ".join(answer.strip().lower().split())
    term = term.strip(".,;:!¡?¿\"'")
    if not term or term.startswith("desconocido"):
        return None
    words = term.split()
    if len(words) > MAX_TERM_WORDS or len(term) > MAX_TERM_CHARS:
        return None
    if any(c.isdigit() for c in term):
        return None
    return term


class ComparePricesUseCase:
    """The price book: every product the user's tickets have ever priced."""

    def __init__(self, receipts: ReceiptRepository) -> None:
        self._receipts = receipts

    def book(self, *, user_id: UUID, query: str | None = None) -> list[ProductPrices]:
        book = build_price_book(self._receipts.all_for_user(user_id))
        return find_product(book, query) if query else book

    def product(self, *, user_id: UUID, product_key: str) -> ProductPrices | None:
        for product in self.book(user_id=user_id):
            if product.product_key == product_key:
                return product
        return None

    def receipt(self, *, user_id: UUID, receipt_id: UUID) -> Receipt | None:
        """One ticket with its lines, or ``None`` when it is not this user's."""
        return self._receipts.get(user_id, receipt_id)


class AnswerPriceQuestion:
    """Streams an answer about prices, grounded in the user's own tickets."""

    def __init__(
        self,
        chat: ChatPort,
        compare: ComparePricesUseCase,
        references: PriceReference | None = None,
        product_terms: "ResolveProductTerms | None" = None,
    ) -> None:
        self._chat = chat
        self._compare = compare
        # Optional so every test that builds this bare keeps working, and so a
        # deployment that wants no outbound call gets one by leaving it out.
        self._references = references or NullPriceReference()
        self._product_terms = product_terms

    @property
    def available(self) -> bool:
        return self._chat.available

    @property
    def model_label(self) -> str:
        return self._chat.model_label

    @property
    def reference_label(self) -> str:
        """Named in the UI beside the model: a second third party sees these
        search terms. One disclosure per party that receives something."""
        return self._references.source_label

    def reference_terms(self, *, user_id: UUID, product_keys: Sequence[str]) -> list[str]:
        """The external search terms for the products the user *attached*.

        Explicit or nothing. Earlier versions guessed the product out of the
        question's prose and were wrong in a new way every week — "Es posible
        conseguir un precio mejor…" begins with a verb. Now the user points at a
        line of their ticket, that line's stored association supplies the word,
        and a question with nothing attached makes no outbound call at all.
        """
        if not self._references.available or not product_keys or self._product_terms is None:
            return []
        book = {p.product_key: p for p in self._compare.book(user_id=user_id)}
        terms: list[str] = []
        for key in list(dict.fromkeys(product_keys))[:REFERENCE_TERMS]:
            product = book.get(key)
            if product is None:
                continue  # not theirs, or not a product: nothing to look up
            term = self._product_terms.resolve(
                user_id=user_id, product_key=key, description=product.name
            )
            if term and term not in terms:
                terms.append(term)
        return terms

    def reference_quotes(
        self, terms: Sequence[str], *, user_id: UUID | None = None, product_keys: Sequence[str] = ()
    ) -> list[PriceQuote]:
        """The blocking half. Empty on any failure — see the port.

        Terms are tried in order and the first that finds anything wins. The
        attached product's printed size travels as a hint, so a source that
        searches pages lands on "detergente 7 l" and not on a category page.
        """
        hint = self.presentation_hint(user_id=user_id, product_keys=product_keys) if user_id else ""
        for term in terms:
            quotes = self._references.lookup([term], hint=hint)
            if quotes:
                return quotes
        return []

    def presentation_hint(self, *, user_id: UUID, product_keys: Sequence[str]) -> str:
        """"7 l" for a jug, "" when the ticket printed no size."""
        book = {p.product_key: p for p in self._compare.book(user_id=user_id)}
        for key in product_keys:
            product = book.get(key)
            point = product.latest if product else None
            if point and point.size is not None and point.size_unit:
                size = str(point.size.normalize()) if hasattr(point.size, "normalize") else str(point.size)
                return f"{size} {point.size_unit}"
        return ""

    def stream(
        self,
        *,
        user_id: UUID,
        question: str,
        history: Sequence[ChatMessage] = (),
        receipt_id: UUID | None = None,
        quotes: Sequence[PriceQuote] = (),
        product_keys: Sequence[str] = (),
    ) -> Iterator[str]:
        brief = self.build_brief(
            user_id=user_id,
            question=question,
            receipt_id=receipt_id,
            quotes=quotes,
            product_keys=product_keys,
        )
        # The brief rides on the user turn rather than in the system prompt, so
        # the system half stays byte-identical between questions and a gateway
        # that caches prefixes can.
        messages = [
            *history,
            ChatMessage(role="user", content=f"{brief}\n\nPregunta: {question.strip()}"),
        ]
        return self._chat.stream(system=SYSTEM, messages=messages)

    def build_brief(
        self,
        *,
        user_id: UUID,
        question: str,
        receipt_id: UUID | None = None,
        quotes: Sequence[PriceQuote] = (),
        product_keys: Sequence[str] = (),
    ) -> str:
        """Everything the model is allowed to know, as plain text.

        ``product_keys`` are the lines the user attached to the question. They
        get the detailed treatment regardless of wording — the user pointed at
        them, which is a stronger signal than any word in the sentence.

        With a ``receipt_id`` the brief is **one basket** rather than the whole
        book — see :meth:`_receipt_brief`. The system prompt is unchanged either
        way, deliberately: it stays byte-identical between questions so a
        gateway that caches prefixes still can, and the scope is data, not
        instruction.

        Two zoom levels, because a price question is almost always about one
        product inside a basket of many: every product gets a summary line, and
        the products the question actually names get their purchases listed one
        by one, with store and date. Public because it is the thing worth
        testing — a brief that omits the store name is how "¿dónde estaba más
        barata?" starts getting answered with a shrug.
        """
        if receipt_id is not None:
            book = self._compare.book(user_id=user_id)
            attached = [p for p in book if p.product_key in set(product_keys)]
            own = self._receipt_brief(
                user_id=user_id, question=question, receipt_id=receipt_id
            )
            subject = "\n".join(self._subject_lines(user_id=user_id, attached=attached))
            return _with_references(f"{subject}\n{own}" if subject else own, quotes)

        book = self._compare.book(user_id=user_id)
        if not book:
            return _with_references(
                "SIN TICKETS: el usuario todavía no ha subido ninguna foto de ticket, "
                "así que no hay ningún precio que comparar.",
                quotes,
            )

        attached = [p for p in book if p.product_key in set(product_keys)]
        mentioned = mentioned_in(book, question) if question.strip() else []
        asked = list(dict.fromkeys([*attached, *mentioned]))[:DETAILED_PRODUCTS]
        lines = self._subject_lines(user_id=user_id, attached=attached)
        lines += [
            f"PRODUCTOS CON PRECIO ({len(book)} en total, se listan hasta {BRIEF_PRODUCTS}):",
            "  formato: producto · compras · base · mediana · mínimo (tienda, fecha) · "
            "máximo (tienda, fecha) · última",
        ]
        lines += [f"  {_summary_line(p)}" for p in book[:BRIEF_PRODUCTS]]

        if asked:
            lines.append("")
            lines.append("DETALLE DE LOS PRODUCTOS QUE MENCIONA LA PREGUNTA:")
            for product in asked:
                lines.append(f"  {product.name} (base: {_basis_label(product)}):")
                lines += [f"    {_point_line(product, p)}" for p in product.points[:DETAIL_POINTS]]
                if len(product.points) > DETAIL_POINTS:
                    lines.append(f"    … {len(product.points) - DETAIL_POINTS} compras más")
        return _with_references("\n".join(lines), quotes)


    def _subject_lines(self, *, user_id: UUID, attached: Sequence[ProductPrices]) -> list[str]:
        """The products the user pointed at, stated before anything else.

        A chip is a stronger signal than any word in the sentence, and the model
        has to be told so in the brief itself -- "¿dónde conseguirlo más barato?"
        has no noun, and without this section the model asks which product,
        which is the one question the chip already answered.
        """
        if not attached:
            return []
        lines = ["PRODUCTOS SEÑALADOS POR EL USUARIO (la pregunta es sobre estos):"]
        for product in attached:
            last = product.latest
            paid = (
                f"pagó ${last.amount} en {last.store or 'tienda no legible'} "
                f"el {last.purchased_at.isoformat() if last.purchased_at else 'fecha no legible'}"
                if last else "sin compra registrada"
            )
            term = self._stored_term(user_id=user_id, product_key=product.product_key)
            searched = f" · buscado en la referencia como «{term}»" if term else ""
            lines.append(f"  {product.name} · {paid}{searched}")
        lines.append("")
        return lines

    def _stored_term(self, *, user_id: UUID, product_key: str) -> str | None:
        if self._product_terms is None:
            return None
        stored = self._product_terms.stored(user_id=user_id, product_key=product_key)
        return stored.term if stored else None

    def _receipt_brief(self, *, user_id: UUID, question: str, receipt_id: UUID) -> str:
        """One basket, plus the history of the products inside it.

        A question asked from inside a ticket is almost always about that
        ticket ("¿qué me salió más caro aquí?"), and handing the model the whole
        pantry to answer it is how a line from a different trip ends up in the
        answer. So the basket is the brief.

        The history is still there, but only for the products this ticket
        actually contains and only when there is more than one purchase to
        compare — which is what lets "¿pagué de más?" be answerable at all
        without reopening the door to every other basket.
        """
        receipt = self._compare.receipt(user_id=user_id, receipt_id=receipt_id)
        if receipt is None:
            # Not an error the model should explain away: it is told the plain
            # fact and the endpoint above has already checked ownership.
            return "TICKET NO ENCONTRADO: no hay ningún ticket con ese id para este usuario."

        store = receipt.store or "tienda no legible"
        when = receipt.purchased_at.isoformat() if receipt.purchased_at else "fecha no legible"
        total = f"${receipt.total}" if receipt.total is not None else "no legible"
        lines = [
            f"ESTE TICKET: {store} · {when} · total impreso {total} · "
            f"{len(receipt.items)} líneas leídas",
            "  formato: producto · cantidad · precio unitario · importe",
        ]
        lines += [f"  {_item_line(item)}" for item in sorted(receipt.items, key=_line_no)]

        # Said out loud for the same reason the UI says it: OCR drops lines, and
        # a basket that does not add up to the printed total is a basket with a
        # line missing. A model that is not told will reconcile it silently.
        lines.append("")
        lines.append(f"  Las líneas suman ${receipt.items_total}.")
        if receipt.total is not None and receipt.total != receipt.items_total:
            missing = receipt.total - receipt.items_total
            lines.append(
                f"  NO CUADRA con el total impreso: faltan ${missing} por leer. "
                "Dilo si la pregunta depende del total."
            )

        keys = {item.product_key for item in receipt.items}
        history = [
            product
            for product in self._compare.book(user_id=user_id)
            if product.product_key in keys and product.times_bought > 1
        ]
        lines.append("")
        if history:
            lines.append("ESTOS PRODUCTOS EN TUS OTROS TICKETS:")
            lines.append(
                "  formato: producto · compras · base · mediana · mínimo (tienda, fecha) · "
                "máximo (tienda, fecha) · última"
            )
            lines += [f"  {_summary_line(p)}" for p in history[:BRIEF_PRODUCTS]]
        else:
            lines.append(
                "SIN HISTORIAL: ningún producto de este ticket aparece en otro ticket, "
                "así que no hay con qué comparar sus precios. Dilo si te lo preguntan."
            )
        return "\n".join(lines)


def _with_references(brief: str, quotes: Sequence[PriceQuote]) -> str:
    """Append the external prices, fenced off from everything above them.

    Its own section, its own heading, every line carrying the source and the
    date. The separation is not decoration: the rest of the brief is what the
    user paid, and one paragraph that mixes the two is a product that can no
    longer say which of its numbers came from a document you own.
    """
    if not quotes:
        return brief
    lines = [
        brief,
        "",
        "PRECIOS DE REFERENCIA (NO son compras del usuario):",
        "  Observaciones publicadas por un tercero, de presentaciones mezcladas "
        "(distintos tamaños y marcas dentro de cada tipo). Sirven para ubicar un "
        "rango, no para una comparación exacta.",
        "  formato: tipo · observaciones · mediana · más barato (cadena) · más caro "
        "(cadena) · fecha · fuente",
    ]
    for quote in quotes:
        observed = quote.observed.isoformat() if quote.observed else "fecha no publicada"
        lines.append(
            f"  {quote.kind} · {quote.observations} observaciones · "
            f"mediana ${quote.median} · más barato ${quote.low} ({quote.low_where}) · "
            f"más caro ${quote.high} ({quote.high_where}) · {observed} · {quote.source}"
        )
        lines.append(f"    el más barato es: {quote.low_label}")
        for u in quote.per_unit:
            # The comparable figure. Same base unit as a ticket line's
            # `per_base_unit`, so "tu garrafón sale a $24.30/L" and "$38.33/L
            # en Bodega" are the same kind of number.
            base = {"l": "litro", "kg": "kilo"}.get(u.unit, "pieza")
            line = (
                f"    por {base}: ${u.per_unit}/{u.unit} · {u.label} · "
                f"${u.price} por {u.size} {u.unit} · {u.where}"
            )
            if u.notes:
                line += " · " + ", ".join(u.notes)
            if u.url:
                line += f" · {u.url}"
            lines.append(line)
    return "\n".join(lines)


# --- brief formatting ----------------------------------------------------
def _line_no(item) -> int:
    return item.line_no


def _item_line(item) -> str:
    """One printed line. Absent figures are named, never blanked."""
    quantity = item.quantity if item.quantity is not None else "no impresa"
    unit = f"${item.unit_price}" if item.unit_price is not None else "no impreso"
    return f"{item.description} · {quantity} · {unit} · ${item.amount}"


def _basis_label(product: ProductPrices) -> str:
    if product.basis != "unit":
        return "por pieza"
    unit = product.points[0].size_unit if product.points else None
    return "por litro" if unit == "l" else "por kilo"


def _summary_line(product: ProductPrices) -> str:
    """One product, one line. Absent figures are said out loud.

    "sin precio unitario" rather than a blank: a model that sees a gap fills
    it, and naming the gap is the instruction that stops it.
    """
    if product.median is None:
        return (
            f"{product.name} · {product.times_bought} compra(s) · "
            "sin precio comparable (el ticket no imprimió cantidad ni tamaño)"
        )
    parts = [
        product.name,
        f"{product.times_bought} compra(s)",
        _basis_label(product),
        f"mediana ${product.median}",
        f"min {_where(product, product.cheapest)}",
        f"max {_where(product, product.dearest)}",
        f"última {_where(product, product.latest)}",
    ]
    if product.spread is not None:
        parts.append(f"diferencia {product.spread}%")
    return " · ".join(parts)


def _where(product: ProductPrices, point) -> str:
    if point is None:
        return "no disponible"
    value = point.value(product.basis)
    store = point.store or "tienda no legible"
    when = point.purchased_at.isoformat() if point.purchased_at else "fecha no legible"
    return f"${value} ({store}, {when})"


def _point_line(product: ProductPrices, point) -> str:
    when = point.purchased_at.isoformat() if point.purchased_at else "fecha no legible"
    store = point.store or "tienda no legible"
    value = point.value(product.basis)
    price = f"${value} {_basis_label(product)}" if value is not None else "sin precio comparable"
    size = f" · tamaño {point.size} {point.size_unit}" if point.size else ""
    quantity = f" · cantidad {point.quantity}" if point.quantity else ""
    return (
        f"{when} · {store} · «{point.description}» · "
        f"importe ${point.amount} · {price}{size}{quantity}"
    )
