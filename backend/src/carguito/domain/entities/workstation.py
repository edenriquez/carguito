from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

#: One clause's whole surface. Deliberately a fixed set of *named* conditions
#: rather than a tree of arbitrary expressions: every one of them maps to a
#: filter the metric catalog already declares, which is what keeps a saved rule
#: and a runnable query the same object. A rule the engine would reject can
#: never be stored.
CLAUSE_FIELDS = ("description_contains", "amount_min", "amount_max", "category_id", "tag_id")

#: Kept under its historical name: the conditions one clause can state have not
#: changed, only how many clauses a rule may carry.
RULE_FIELDS = CLAUSE_FIELDS

#: How many clauses one rule may union. The cap is a product judgement like
#: MAX_EXCLUSIONS below: a set assembled from fifteen unrelated searches is not
#: a lens any more, and no reader can hold what it means.
MAX_CLAUSES = 10

#: Above this many hand-excluded rows, the rule is wrong and the exclusions are
#: papering over it. The cap is a product judgement, not a storage limit: a
#: workstation is a lens, and a lens with 200 exceptions is a list.
MAX_EXCLUSIONS = 200


@dataclass(slots=True)
class RuleClause:
    """One filter: the conditions that must hold *together*.

    Every condition is optional and they compose as AND -- "contains 'recarga'
    *and* between 10 and 300". A clause is the unit the editor shows as one
    block, and the unit a user reasons about; the union of several of them is
    what makes a group (see :class:`WorkstationRule`).
    """

    description_contains: str | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    category_id: UUID | None = None
    tag_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.description_contains is not None:
            self.description_contains = self.description_contains.strip()
            if not self.description_contains:
                # An empty needle matches every movement. That is never what a
                # filter meant, and a set that silently becomes "all your money"
                # is worse than a rejected save.
                raise ValueError("description_contains must not be empty.")

        self.amount_min = _amount(self.amount_min, "amount_min")
        self.amount_max = _amount(self.amount_max, "amount_max")
        if self.amount_min is not None and self.amount_max is not None:
            if self.amount_min > self.amount_max:
                raise ValueError(
                    f"amount_min ({self.amount_min}) is above amount_max ({self.amount_max}); "
                    "no movement can satisfy that."
                )

        if self.category_id is not None and not isinstance(self.category_id, UUID):
            self.category_id = UUID(str(self.category_id))
        if self.tag_id is not None and not isinstance(self.tag_id, UUID):
            self.tag_id = UUID(str(self.tag_id))

        if not self.conditions:
            # A clause with no conditions is the whole ledger wearing a name.
            # Movimientos already shows that, better.
            raise ValueError("A rule needs at least one condition.")

    @property
    def conditions(self) -> dict[str, Any]:
        """The stated conditions, in domain types. Absent keys are unset."""
        return {
            name: value
            for name, value in (
                (field_name, getattr(self, field_name)) for field_name in CLAUSE_FIELDS
            )
            if value is not None
        }

    def to_filters(self) -> dict[str, Any]:
        """This clause as metric-query filters, under the catalog's names."""
        filters: dict[str, Any] = {}
        if self.description_contains:
            filters["description_contains"] = self.description_contains
        if self.amount_min is not None:
            filters["amount_min"] = str(self.amount_min)
        if self.amount_max is not None:
            filters["amount_max"] = str(self.amount_max)
        if self.category_id:
            filters["category"] = str(self.category_id)
        if self.tag_id:
            filters["tag"] = str(self.tag_id)
        return filters

    def to_json(self) -> dict[str, str]:
        """The clause as JSON. Decimals and UUIDs go out as strings.

        JSON's float would not carry an amount bound back unchanged, and a bound
        that drifts by a centavo silently changes which movements are in the set.
        """
        return {name: str(value) for name, value in self.conditions.items()}

    @classmethod
    def from_json(cls, raw: Any) -> RuleClause:
        if not isinstance(raw, dict):
            raise ValueError("Each filter must be an object")
        unknown = set(raw) - set(CLAUSE_FIELDS)
        if unknown:
            raise ValueError(f"Unsupported rule conditions: {sorted(unknown)}")
        return cls(
            description_contains=raw.get("description_contains"),
            amount_min=raw.get("amount_min"),
            amount_max=raw.get("amount_max"),
            category_id=_uuid_or_none(raw.get("category_id")),
            tag_id=_uuid_or_none(raw.get("tag_id")),
        )


class WorkstationRule:
    """What makes a movement part of this set: one clause, or the union of several.

    A single clause is the original design and still the common case -- "contains
    'recarga' and between 10 and 300". Several clauses are a **group**: a user
    who thinks of "mis suscripciones" as spotify *plus* netflix *plus* the gym
    charge was, before this existed, forced to keep three separate lenses and add
    the totals by hand, which is arithmetic the product exists to remove.

    The union is deliberately flat -- clauses of ANDs OR'd together, never
    nested. That is one level of structure, which is what a person can read off
    a screen and still trust the number under it. `excluded_tx_ids` on the
    workstation stays global: an exclusion says "not this movement", which is
    true regardless of which clause let it in.
    """

    __slots__ = ("clauses",)

    def __init__(self, clauses: Any = None, **flat: Any) -> None:
        if clauses is not None:
            if flat:
                raise ValueError("Pass either `clauses` or the conditions of one clause.")
            if not isinstance(clauses, (list, tuple)):
                raise ValueError("'clauses' must be a list of filters")
            parsed = [
                clause if isinstance(clause, RuleClause) else RuleClause.from_json(clause)
                for clause in clauses
            ]
        else:
            # The single-clause constructor every caller used before groups
            # existed: `WorkstationRule(description_contains="recarga")`.
            parsed = [RuleClause(**flat)]

        if not parsed:
            raise ValueError("A rule needs at least one condition.")
        if len(parsed) > MAX_CLAUSES:
            raise ValueError(
                f"A rule unions at most {MAX_CLAUSES} filters; got {len(parsed)}. "
                "Widen one of them instead."
            )
        self.clauses = parsed

    @property
    def is_group(self) -> bool:
        """True when the rule unions more than one filter."""
        return len(self.clauses) > 1

    def to_filters(self, excluded: list[UUID]) -> dict[str, Any]:
        """The rule as a metric-query ``filters`` dict.

        This method is the whole reason the rule is modelled rather than stored
        as opaque JSON: a saved rule and a runnable query are the same thing in
        two shapes, and the translation lives in exactly one place. The names on
        the right are the catalog's, so drift between them is an import error
        rather than an empty widget.

        A one-clause rule compiles exactly as it always did -- flat, no wrapper.
        Every stored lens and every saved dashboard keeps producing the identical
        query, and `any_of` appears only for a rule that actually needs it.
        """
        filters: dict[str, Any] = {}
        if self.is_group:
            filters["any_of"] = [clause.to_filters() for clause in self.clauses]
        else:
            filters.update(self.clauses[0].to_filters())
        if excluded:
            filters["exclude_tx"] = [str(tx_id) for tx_id in excluded]
        return filters

    def to_json(self) -> dict[str, Any]:
        """The rule as the JSON column holds it, and as the client reads it.

        Flat for one clause, so rows written before groups existed round-trip
        unchanged and clients that only ever knew the flat shape keep working.
        """
        if self.is_group:
            return {"any_of": [clause.to_json() for clause in self.clauses]}
        return self.clauses[0].to_json()

    @classmethod
    def from_json(cls, raw: Any) -> WorkstationRule:
        """Parse either shape. The one place that knows both."""
        if not isinstance(raw, dict):
            raise ValueError("'rule' must be an object")
        if "any_of" in raw:
            alongside = set(raw) - {"any_of"}
            if alongside:
                # Half-group, half-flat would have two readings ("and" or "or"),
                # and a rule nobody can read at a glance is one whose numbers
                # stop being trusted.
                raise ValueError(
                    f"'any_of' is the whole rule; unsupported alongside it: {sorted(alongside)}"
                )
            items = raw["any_of"]
            if not isinstance(items, list) or not items:
                raise ValueError("'any_of' must be a non-empty list of filters")
            return cls(clauses=items)
        return cls(clauses=[raw])

    def __eq__(self, other: object) -> bool:
        return isinstance(other, WorkstationRule) and self.clauses == other.clauses

    def __repr__(self) -> str:
        return f"WorkstationRule(clauses={self.clauses!r})"


@dataclass(slots=True)
class Workstation:
    """A user's saved lens over the ledger: a rule, a name, and its exceptions.

    ``excluded_tx_ids`` is not a second rule -- it is the escape hatch a text
    predicate always eventually needs. A user who matched 47 movements and knows
    two of them are not top-ups must be able to say so without abandoning the
    rule that got them the other 45.
    """

    user_id: UUID
    name: str
    rule: WorkstationRule
    excluded_tx_ids: list[UUID] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Workstation name must not be empty.")
        if len(self.name) > 120:
            raise ValueError("Workstation name must be 120 characters or fewer.")

        # Order-independent and duplicate-free: two saves of the same set of
        # exclusions must produce the same row, or every diff is noise.
        self.excluded_tx_ids = sorted(set(self.excluded_tx_ids), key=str)
        if len(self.excluded_tx_ids) > MAX_EXCLUSIONS:
            raise ValueError(
                f"A workstation carries at most {MAX_EXCLUSIONS} manual exclusions; "
                f"got {len(self.excluded_tx_ids)}. Narrow the rule instead."
            )

    def to_filters(self) -> dict[str, Any]:
        """The filters every metric read of this workstation is made under."""
        return self.rule.to_filters(self.excluded_tx_ids)


def _amount(value: Any, name: str) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number, got {value!r}.") from exc
    if amount < 0:
        # Amounts are magnitudes here, as everywhere in this domain: direction
        # lives in tx_type. A negative bound would silently match nothing.
        raise ValueError(f"{name} must not be negative, got {amount}.")
    return amount


def _uuid_or_none(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, UUID) else UUID(str(value))
