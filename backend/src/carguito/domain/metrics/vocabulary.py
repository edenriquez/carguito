"""The closed vocabulary: every measure, dimension, filter and grain that exists.

Semantic names only. ``Measure.column`` and friends name a *semantic* column;
the DuckDB adapter owns the mapping to physical SQL. Nothing outside these
dictionaries can reach a query.
"""

from __future__ import annotations

from .spec import Dimension, Eq, FilterDef, Grain, Measure

# Default filters (docs/redesign-plan.md §1) attach to the measure so that
# "spend excludes what the user excluded" is declared once and inherited by
# every metric that sums money, rather than remembered in nine places. The
# remaining member, `is_primary_in_group` (fingerprint dedup), arrives with B10.
_LEDGER_DEFAULTS = (
    # The user's own opinion about a row. Honoured everywhere, immediately:
    # an exclusion that does not move the number on screen reads as a bug.
    Eq("excluded_from_stats", False),
    # A card payment is not spend -- the card's own charges already are, and
    # counting both is the same pesos twice (§2). Declared here, once, which is
    # the property that pays for this whole abstraction: with nine bespoke
    # endpoints, nine places would have to remember it and one would not.
    Eq("is_transfer", False),
)

MEASURES: dict[str, Measure] = {
    "expense_amount": Measure(
        name="expense_amount",
        column="amount",
        agg="sum",
        direction="expense",
        default_filters=_LEDGER_DEFAULTS,
    ),
    "income_amount": Measure(
        name="income_amount",
        column="amount",
        agg="sum",
        direction="income",
        default_filters=_LEDGER_DEFAULTS,
    ),
    # Signed: income positive, expense negative. The only measure that may go
    # below zero, which is the point of it.
    "net_amount": Measure(
        name="net_amount",
        column="amount",
        agg="sum",
        direction="net",
        default_filters=_LEDGER_DEFAULTS,
    ),
    # How many rows the set actually has. `expense_amount` alone cannot answer
    # "what does one of these usually cost" -- a total of 260 is four top-ups or
    # one plan, and the whole point of a saved lens is telling those apart.
    "tx_count": Measure(
        name="tx_count",
        column="tx_id",
        agg="count",
        direction="expense",
        default_filters=_LEDGER_DEFAULTS,
    ),
    # The shape of the habit, not its size. Together with the mean these are
    # what a "how much should I put in each time" question is actually about.
    "expense_min": Measure(
        name="expense_min",
        column="amount",
        agg="min",
        direction="expense",
        default_filters=_LEDGER_DEFAULTS,
    ),
    "expense_max": Measure(
        name="expense_max",
        column="amount",
        agg="max",
        direction="expense",
        default_filters=_LEDGER_DEFAULTS,
    ),
    # Median rather than mean for the typical charge: one 200-peso plan among
    # twenty 15-peso top-ups moves the mean by a quarter and the median not at
    # all, and it is the median that describes the habit.
    "expense_median": Measure(
        name="expense_median",
        column="amount",
        agg="median",
        direction="expense",
        default_filters=_LEDGER_DEFAULTS,
    ),
    # Cash out of an ATM. Its own measure rather than a client-supplied filter,
    # because "which rows count as withdrawn cash" is a definition (fees are
    # not cash) and definitions belong to the measure, not to the caller.
    "withdrawal_amount": Measure(
        name="withdrawal_amount",
        column="amount",
        agg="sum",
        direction="expense",
        default_filters=(
            Eq("excluded_from_stats", False),
            Eq("is_cash_withdrawal", True),
        ),
    ),
}

DIMENSIONS: dict[str, Dimension] = {
    "category": Dimension(
        name="category",
        column="category_name",
        label="Categoria",
        key_column="category_id",
    ),
    "month": Dimension(name="month", column="tx_month", label="Mes"),
    "currency": Dimension(name="currency", column="currency", label="Moneda"),
    "tx_type": Dimension(name="tx_type", column="tx_type", label="Tipo"),
    # The one overlapping axis: tags are many-per-transaction on purpose.
    "tag": Dimension(
        name="tag",
        column="tag_name",
        label="Etiqueta",
        key_column="tag_id",
        overlapping=True,
    ),
}

FILTERS: dict[str, FilterDef] = {
    "category": FilterDef(name="category", column="category_id"),
    "currency": FilterDef(name="currency", column="currency"),
    "tx_type": FilterDef(name="tx_type", column="tx_type"),
    # Filtering reads the denormalised array on the fact row; only *grouping*
    # by tag needs the bridge join. That is why the cube keeps both.
    "tag": FilterDef(name="tag", column="tag_ids", multivalued=True),
    # By source statement — the seam bank/account scoping reaches through.
    # Statement ids rather than bank names: the id is immutable while the
    # bank label is user-editable, and a rename must not strand old facts.
    "statement": FilterDef(name="statement", column="statement_id"),
    # --- the workstation predicates -------------------------------------
    # A saved lens over the ledger ("my phone top-ups") cannot be expressed in
    # ids alone: the thing that makes a top-up a top-up is its wording. These
    # four are what let a user define a set the product never anticipated,
    # while the vocabulary stays closed — a client still sends a declared name,
    # never an expression.
    #
    # Matches `description`, the alias the user sees and can rewrite, not
    # `raw_description`. Someone who renamed "TELCEL*RECARGA" to "Recarga
    # Telcel" must find their set by what they typed.
    "description_contains": FilterDef(
        name="description_contains", column="description", ops=("contains",)
    ),
    # Both bounds inclusive, over the magnitude — `amount` is unsigned here, so
    # these read the same for spend and income and never need a sign caveat.
    "amount_min": FilterDef(name="amount_min", column="amount", ops=("gte",)),
    "amount_max": FilterDef(name="amount_max", column="amount", ops=("lte",)),
    # The escape hatch every rule needs: a predicate over free text will catch
    # something it shouldn't, and the user must be able to say so per row
    # without abandoning the rule that got them 95% there.
    "exclude_tx": FilterDef(name="exclude_tx", column="tx_id", ops=("not_in",)),
}

GRAINS: dict[str, Grain] = {
    "day": Grain(name="day", column="tx_date"),
    "month": Grain(name="month", column="tx_date"),
}
