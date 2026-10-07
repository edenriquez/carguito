"""CRUD for a user's saved lenses over the ledger.

The load-bearing part is not the CRUD -- it is :func:`validate_rule`. Every save
runs the rule through the *same* catalog validation the query path runs, so a
workstation is by construction a workstation that can be read. This is the
property ``SaveHomeDashboardUseCase`` established for layouts ("a layout is only
saveable if it is queryable") and it matters more here: a dashboard widget that
cannot render is one broken card, while a rule that cannot compile is a view
whose every number is missing with no way for the user to tell why.

Failing at save is the point. A 400 while editing a rule is legible; a rule that
saves and then produces an empty panel forever is not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from ...domain.entities import Workstation, WorkstationRule
from ...domain.metrics.catalog import COHORT_PROFILE, METRIC_CATALOG
from ...domain.metrics.spec import MetricSpec, MetricValidationError
from ...domain.metrics.vocabulary import FILTERS
from ..ports.outbound import ConversationRepository, WorkstationRepository


class WorkstationNotFound(LookupError):
    """No workstation with that id belongs to this user.

    A missing row and someone else's row are the same answer on purpose: the
    404 must not tell a caller that an id exists but is not theirs.
    """


def validate_rule(
    rule: WorkstationRule,
    excluded: Sequence[UUID],
    catalog: Mapping[str, MetricSpec] = METRIC_CATALOG,
) -> None:
    """Raise unless the rule compiles to a query ``cohort_profile`` accepts.

    Validated against `cohort_profile` specifically because that is the metric
    every workstation is read through; if its declared filter list ever drifts
    from what a rule can express, this raises at save rather than leaving a
    saved rule that silently returns nothing.
    """
    spec = catalog[COHORT_PROFILE.id]
    # Raises MetricValidationError on an undeclared filter name or a value the
    # op refuses -- the same check the query endpoint runs, against the same
    # vocabulary. A ValueError subclass, so it lands on the app-wide 400.
    spec.validate_filters(rule.to_filters(list(excluded)), FILTERS)


class ManageWorkstations:
    """List, read, create, update and delete a user's workstations."""

    def __init__(
        self,
        workstations: WorkstationRepository,
        conversations: ConversationRepository | None = None,
    ) -> None:
        self._workstations = workstations
        # Optional so the many tests that construct this use case bare keep
        # working; production wiring always passes it.
        self._conversations = conversations

    def list(self, *, user_id: UUID) -> list[Workstation]:
        return self._workstations.list_for_user(user_id)

    def get(self, *, user_id: UUID, workstation_id: UUID) -> Workstation:
        workstation = self._workstations.get(user_id, workstation_id)
        if workstation is None:
            raise WorkstationNotFound(str(workstation_id))
        return workstation

    def create(
        self,
        *,
        user_id: UUID,
        name: str,
        rule: WorkstationRule,
        excluded_tx_ids: Sequence[UUID] = (),
    ) -> Workstation:
        # The entity validates its own shape (non-empty needle, min <= max, at
        # least one condition); this validates that the shape is *runnable*.
        # Both, in that order, before anything touches storage.
        workstation = Workstation(
            user_id=user_id,
            name=name,
            rule=rule,
            excluded_tx_ids=list(excluded_tx_ids),
        )
        validate_rule(workstation.rule, workstation.excluded_tx_ids)
        self._workstations.add(workstation)
        # Read it back rather than returning the in-memory object: `created_at`
        # and `updated_at` are set by the database, and a POST response that
        # says `null` for both is a response the client cannot sort by.
        return self.get(user_id=user_id, workstation_id=workstation.id)

    def update(
        self,
        *,
        user_id: UUID,
        workstation_id: UUID,
        name: str | None = None,
        rule: WorkstationRule | None = None,
        excluded_tx_ids: Sequence[UUID] | None = None,
    ) -> Workstation:
        """Patch semantics: an omitted field is left alone, not cleared.

        The rule, though, is replaced wholesale when given. A rule is a single
        thought -- "top-ups between 10 and 300" -- and merging a partial one
        into a stored one produces a set the user never described.
        """
        current = self.get(user_id=user_id, workstation_id=workstation_id)

        updated = Workstation(
            id=current.id,
            user_id=current.user_id,
            name=current.name if name is None else name,
            rule=current.rule if rule is None else rule,
            excluded_tx_ids=(
                list(current.excluded_tx_ids)
                if excluded_tx_ids is None
                else list(excluded_tx_ids)
            ),
            created_at=current.created_at,
        )
        validate_rule(updated.rule, updated.excluded_tx_ids)
        self._workstations.replace(updated)
        # Same reason as create: `updated_at` moved, and only the database
        # knows where to.
        return self.get(user_id=user_id, workstation_id=updated.id)

    def delete(self, *, user_id: UUID, workstation_id: UUID) -> None:
        if not self._workstations.delete(user_id, workstation_id):
            raise WorkstationNotFound(str(workstation_id))
        # The lens takes its conversations with it: a thread about a set that
        # no longer exists has nothing left to be about.
        if self._conversations is not None:
            self._conversations.delete_for_workstation(user_id, workstation_id)


__all__ = [
    "ManageWorkstations",
    "MetricValidationError",
    "WorkstationNotFound",
    "validate_rule",
]
