"""Declarative vocabulary for the metric registry (docs/redesign-plan.md §1).

Pure domain: no SQL, no Flask, no DuckDB. A :class:`MetricSpec` says *what* a
metric means -- which measures it selects, which dimensions and filters a client
may combine with it, what shape comes back -- in **semantic** names only. The
name-to-column mapping belongs to the adapter
(``adapters/outbound/cube/duckdb_metric_engine.py``), which is what keeps the
catalog a business definition rather than a query template.

The catalog is *closed*: a client sends a metric id plus identifiers drawn from
this vocabulary and never an expression. Everything outside it is rejected here,
before a compiler ever sees it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

MetricQuality = Literal["estimate", "beta"]

MetricKind = Literal["aggregation", "computed"]
#: ``table`` is rows that are not a measure over an axis -- one row per
#: *statement about the data* rather than per bucket of it. The advisor's
#: principles are the first: a row is a sentence plus the numbers that justify
#: it, and calling that a "breakdown" would promise a total it does not have.
MetricShape = Literal["scalar", "series", "breakdown", "table"]
#: ``min``/``max``/``median`` describe a *distribution* rather than a total:
#: "what does one of these usually cost", which is the question a saved lens
#: over a habit is really asking. Unlike the sums they cannot be expressed as a
#: signed CASE, so they are only valid on a direction-homogeneous metric -- the
#: compiler enforces that rather than trusting the catalog.
Aggregation = Literal["sum", "count", "min", "max", "median"]
#: Which side of the ledger a measure reads. ``net`` signs income positive and
#: expense negative; ``any`` ignores direction entirely.
Direction = Literal["expense", "income", "net", "any"]
#: ``eq``/``in`` are the historical pair and travel together: a scalar value
#: compiles to equality, a list to membership, and the caller picks by what it
#: sends. Every op added since names exactly **one** predicate, so a filter that
#: declares one of them declares its whole compilation.
FilterOp = Literal["eq", "in", "contains", "gte", "lte", "not_in"]
ParamType = Literal["decimal", "int", "float"]

#: How many groups one ``any_of`` may union. A query-safety bound, deliberately
#: stated here rather than imported from the workstation entity: that module's
#: ``MAX_CLAUSES`` is a product judgement about what a person can read, this one
#: is about what the compiler will build. They happen to agree today.
MAX_ANY_OF = 10

#: Filters that scope the *whole* query and are meaningless inside one group of
#: a union. Currency is the reading's unit, `exclude_tx` says "not this
#: movement" no matter which group let it in, and a nested `any_of` would be the
#: tree this design refuses.
NOT_INSIDE_ANY_OF = frozenset({"any_of", "currency", "exclude_tx"})


class MetricValidationError(ValueError):
    """A query asked for something the catalog does not declare.

    Subclasses ``ValueError`` so a single-metric caller (dashboard validation)
    gets the app-wide 400 handler for free, while the batch query endpoint
    catches it per query and degrades that one widget instead of the request.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Eq:
    """A default equality filter carried by a measure.

    Semantic field name; the adapter resolves it to a column. Declared on the
    *measure* rather than the metric so that "spend excludes transfers" is
    stated once and inherited by every metric that sums spend.
    """

    field: str
    value: Any


@dataclass(frozen=True)
class Measure:
    """A quantity that can be aggregated: semantic column + aggregation."""

    name: str
    column: str
    agg: Aggregation = "sum"
    direction: Direction = "any"
    #: Applied by the compiler to *every* metric that selects this measure.
    default_filters: tuple[Eq, ...] = ()


@dataclass(frozen=True)
class Dimension:
    """An axis a measure can be broken down by."""

    name: str
    column: str
    label: str
    #: Semantic column holding a stable id for the dimension member, when the
    #: label alone is not addressable (category name vs category id).
    key_column: str | None = None
    #: A transaction can belong to more than one member of this axis, so the
    #: rows do **not** partition the total -- one transaction with three tags
    #: appears three times. Surfaced to the client as ``meta.overlapping``;
    #: without it someone ships a pie chart summing to 240%.
    overlapping: bool = False


@dataclass(frozen=True)
class FilterDef:
    """A predicate a client may attach to a query."""

    name: str
    column: str
    ops: tuple[FilterOp, ...] = ("eq", "in")
    #: The column holds a *list*, so the predicate is membership rather than
    #: equality: ``tag = "viaje"`` means "is tagged viaje", not "has exactly one
    #: tag, viaje".
    multivalued: bool = False

    @property
    def op(self) -> FilterOp | None:
        """The single op that compiles this filter, or ``None`` for eq/in.

        The compiler reads the predicate off the *declaration* rather than
        re-deriving it from the value's Python type. That is what keeps
        ``amount_min=500`` a ``>=`` instead of silently becoming an ``=`` the
        day someone sends a scalar where a range was meant.
        """
        return self.ops[0] if len(self.ops) == 1 else None

    def validate_value(self, value: Any) -> Any:
        """Type-check a client value against this filter's op.

        Returns the value the compiler should bind. Raises rather than coercing
        loosely: ``amount_min="mucho"`` must be a 400, not a silent 0 that
        widens the set to everything.
        """
        op = self.op
        if op in ("gte", "lte"):
            if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
                raise MetricValidationError(
                    "filter_invalid",
                    f"Filter '{self.name}' takes a number, got {value!r}.",
                )
            try:
                return Decimal(str(value))
            except InvalidOperation as exc:
                raise MetricValidationError(
                    "filter_invalid",
                    f"Filter '{self.name}' takes a number, got {value!r}.",
                ) from exc

        if op == "contains":
            if not isinstance(value, str) or not value.strip():
                raise MetricValidationError(
                    "filter_invalid",
                    f"Filter '{self.name}' takes a non-empty string, got {value!r}.",
                )
            return value.strip()

        if op == "not_in":
            values = value if isinstance(value, (list, tuple)) else [value]
            if not all(isinstance(v, str) for v in values):
                raise MetricValidationError(
                    "filter_invalid",
                    f"Filter '{self.name}' takes a list of ids, got {value!r}.",
                )
            return list(values)

        return value


@dataclass(frozen=True)
class Grain:
    """A time bucket. ``column`` is the semantic date column it buckets."""

    name: str
    column: str


@dataclass(frozen=True)
class ParamDef:
    """A scalar input to a *computed* metric.

    Params exist because some metrics are functions of user-entered numbers
    rather than of the fact table -- a projection needs a balance and a rate,
    and neither appears in any statement.
    """

    name: str
    type: ParamType
    required: bool = False
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class MetricSpec:
    """One entry in the catalog.

    ``kind`` is the only thing that decides who executes it -- SQL compiler or
    Python resolver -- and it is deliberately invisible to the client, so a
    metric can migrate from resolver to SQL later without a client change.
    """

    id: str
    title: str
    description: str
    group: str
    kind: MetricKind
    shape: MetricShape
    unit: str
    #: Semantic measure names, in output order. Empty for computed metrics.
    measures: tuple[str, ...] = ()
    #: Allowed (not required) dimensions, filters and grains.
    dimensions: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    grains: tuple[str, ...] = ()
    params: tuple[ParamDef, ...] = ()
    default_dimensions: tuple[str, ...] = ()
    default_grain: str | None = None
    #: Running total over the grain axis, rather than a per-bucket value.
    cumulative: bool = False
    #: Capability strings the UI uses to lock a widget it cannot yet fill:
    #: "transactions", "months:3", "cfdi", "tags", "balance".
    requires: tuple[str, ...] = ()
    #: How much to trust the number. ``estimate`` means it rests on a
    #: heuristic over free text rather than on a field the bank stated; the
    #: plan makes the header tag **mandatory** for cash withdrawals and
    #: anomalies (§4). Published in the catalog so the frame can render it
    #: without knowing which metric it is showing.
    quality: Literal["estimate", "beta"] | None = None
    #: The request period does not apply. "Lifetime in vs out" is a claim about
    #: all of history; silently narrowing it to the dashboard's month would
    #: answer a different question with the same label.
    ignores_period: bool = False

    # --- validation ------------------------------------------------------
    def validate_dimensions(self, dimensions: tuple[str, ...]) -> None:
        for name in dimensions:
            if name not in self.dimensions:
                raise MetricValidationError(
                    "dimension_not_allowed",
                    f"Metric '{self.id}' does not support dimension '{name}'. "
                    f"Allowed: {list(self.dimensions)}.",
                )

    def validate_filters(self, filters: dict[str, Any], vocabulary=None) -> dict[str, Any]:
        """Reject undeclared filters, type-check the declared ones.

        Returns the coerced dict the compiler should bind, so a value can never
        reach SQL without having passed the op's own check. ``vocabulary`` is
        injected rather than imported to keep this module free of its own
        registry (the two would import each other otherwise).
        """
        coerced: dict[str, Any] = {}
        for name, value in filters.items():
            if name not in self.filters:
                raise MetricValidationError(
                    "filter_not_allowed",
                    f"Metric '{self.id}' does not support filter '{name}'. "
                    f"Allowed: {list(self.filters)}.",
                )
            if name == "any_of":
                coerced[name] = self._validate_any_of(value, vocabulary)
                continue
            filter_def = (vocabulary or {}).get(name)
            coerced[name] = filter_def.validate_value(value) if filter_def else value
        return coerced

    def _validate_any_of(self, value: Any, vocabulary=None) -> list[dict[str, Any]]:
        """Type-check a union of filter groups.

        ``any_of`` is the one filter whose value is other filters: a list of
        objects, each an AND of ordinary declared filters, OR'd together. The
        vocabulary stays closed all the way down -- every inner name is checked
        against this metric's own allow-list and coerced by its own op, so
        nesting buys a client no predicate it could not already send flat.

        One level only. A tree of unions and intersections is a query language,
        and the moment a set needs one, nobody trusts the number under it.
        """
        if not isinstance(value, (list, tuple)) or not value:
            raise MetricValidationError(
                "filter_invalid",
                f"Filter 'any_of' takes a non-empty list of filter objects, got {value!r}.",
            )
        if len(value) > MAX_ANY_OF:
            raise MetricValidationError(
                "filter_invalid",
                f"Filter 'any_of' unions at most {MAX_ANY_OF} groups, got {len(value)}.",
            )

        groups: list[dict[str, Any]] = []
        for group in value:
            if not isinstance(group, dict) or not group:
                raise MetricValidationError(
                    "filter_invalid",
                    f"Each 'any_of' entry must be a non-empty object of filters, got {group!r}.",
                )
            coerced: dict[str, Any] = {}
            for name, inner in group.items():
                if name in NOT_INSIDE_ANY_OF:
                    raise MetricValidationError(
                        "filter_not_allowed",
                        f"Filter '{name}' scopes the whole query and cannot appear "
                        "inside 'any_of'.",
                    )
                if name not in self.filters:
                    raise MetricValidationError(
                        "filter_not_allowed",
                        f"Metric '{self.id}' does not support filter '{name}'. "
                        f"Allowed: {list(self.filters)}.",
                    )
                filter_def = (vocabulary or {}).get(name)
                coerced[name] = filter_def.validate_value(inner) if filter_def else inner
            groups.append(coerced)
        return groups

    def validate_grain(self, grain: str | None) -> None:
        if grain is not None and grain not in self.grains:
            raise MetricValidationError(
                "grain_not_allowed",
                f"Metric '{self.id}' does not support grain '{grain}'. "
                f"Allowed: {list(self.grains)}.",
            )

    def coerce_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate and type-coerce client params. Raises on anything unknown.

        Returns a new dict containing exactly the declared params, so a
        resolver can index it without defaulting.
        """
        declared = {p.name: p for p in self.params}
        for name in params:
            if name not in declared:
                raise MetricValidationError(
                    "param_not_allowed",
                    f"Metric '{self.id}' does not accept param '{name}'. "
                    f"Allowed: {sorted(declared)}.",
                )

        coerced: dict[str, Any] = {}
        for name, spec in declared.items():
            if name not in params or params[name] is None:
                if spec.required:
                    raise MetricValidationError(
                        "param_required", f"Metric '{self.id}' requires param '{name}'."
                    )
                coerced[name] = spec.default
                continue
            coerced[name] = self._coerce_one(spec, params[name])
        return coerced

    def _coerce_one(self, spec: ParamDef, raw: Any) -> Any:
        try:
            if spec.type == "decimal":
                value: Any = Decimal(str(raw))
            elif spec.type == "int":
                value = int(raw)
            else:
                value = float(raw)
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise MetricValidationError(
                "param_invalid",
                f"Param '{spec.name}' of metric '{self.id}' must be a {spec.type}, got {raw!r}.",
            ) from exc

        numeric = float(value)
        if spec.minimum is not None and numeric < spec.minimum:
            raise MetricValidationError(
                "param_out_of_range",
                f"Param '{spec.name}' must be >= {spec.minimum}, got {raw!r}.",
            )
        if spec.maximum is not None and numeric > spec.maximum:
            raise MetricValidationError(
                "param_out_of_range",
                f"Param '{spec.name}' must be <= {spec.maximum}, got {raw!r}.",
            )
        return value


def normalize(spec: MetricSpec, query):
    """Validate ``query`` against ``spec`` and fill in the spec's defaults.

    Kept next to the spec (rather than in the use case) because "which
    dimension does this metric use when the client names none" is part of the
    metric's definition. ``query`` is an application DTO, typed structurally to
    avoid the domain importing the application layer.
    """
    from .vocabulary import FILTERS  # local: vocabulary imports this module

    spec.validate_dimensions(tuple(query.dimensions))
    filters = spec.validate_filters(dict(query.filters), FILTERS)
    spec.validate_grain(query.grain)
    if spec.kind == "aggregation" and query.params:
        raise MetricValidationError(
            "param_not_allowed",
            f"Metric '{spec.id}' is an aggregation and takes no params.",
        )
    return replace(
        query,
        dimensions=tuple(query.dimensions) or spec.default_dimensions,
        filters=filters,
        grain=query.grain or spec.default_grain,
    )
