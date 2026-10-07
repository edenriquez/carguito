from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from ....domain.metrics.spec import MetricSpec
from ...dtos.metrics import MetricQuery, MetricResult, ResolverContext


@runtime_checkable
class MetricEngine(Protocol):
    """Executes an *aggregation* metric: measure x dimension x filter -> SQL.

    One port, one adapter. Everything the engine needs to know about physical
    storage stays behind it, which is what makes "move the cube to Postgres"
    a one-file change.
    """

    def execute(self, user_id: UUID, spec: MetricSpec, query: MetricQuery) -> MetricResult: ...


@runtime_checkable
class MetricResolver(Protocol):
    """Executes a *computed* metric: a Python function over params.

    A SQL layer cannot express "project this balance forward at an annual rate";
    without resolvers those metrics become bespoke endpoints again and the
    catalog stops being the whole story.
    """

    #: The catalog id this resolver answers for.
    metric_id: str

    def resolve(
        self, user_id: UUID, query: MetricQuery, ctx: ResolverContext
    ) -> MetricResult: ...
