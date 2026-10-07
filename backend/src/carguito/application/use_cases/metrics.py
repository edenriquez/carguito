from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from uuid import UUID

from ...domain.metrics.catalog import METRIC_CATALOG
from ...domain.metrics.spec import MetricSpec, MetricValidationError, normalize
from ..dtos.metrics import (
    MetricBatchResult,
    MetricError,
    MetricQuery,
    MetricResult,
    ResolverContext,
)
from ..ports.outbound.metrics import MetricEngine, MetricResolver

logger = logging.getLogger(__name__)


class RunMetricQueriesUseCase:
    """Validates, dispatches and isolates a batch of metric queries.

    Two properties this exists to guarantee:

    * **Failures are per query.** The command center renders a dozen widgets
      from one request; one metric raising must return an error object for that
      key and leave the other eleven rendered. Nothing here re-raises.
    * **The user is never a parameter of the request.** ``user_id`` is injected
      from the authenticated session and pushed down to the engine. There is no
      code path by which a client-supplied field becomes the tenant scope --
      ``user_id`` is not in the filter vocabulary, so naming it is a rejected
      filter rather than a leak.
    """

    def __init__(
        self,
        *,
        engine: MetricEngine,
        resolvers: Sequence[MetricResolver] = (),
        catalog: Mapping[str, MetricSpec] = METRIC_CATALOG,
    ) -> None:
        self._engine = engine
        self._resolvers = {r.metric_id: r for r in resolvers}
        self._catalog = catalog

    def execute(self, *, user_id: UUID, queries: Sequence[MetricQuery]) -> MetricBatchResult:
        results: dict[str, MetricResult | MetricError] = {}
        for query in queries:
            try:
                results[query.key] = self._run_one(user_id, query)
            except MetricValidationError as exc:
                results[query.key] = MetricError(
                    metric_id=query.metric, code=exc.code, message=exc.message
                )
            except Exception:  # deliberate: one bad widget must not 500 the batch
                logger.exception("Metric '%s' (key %s) failed", query.metric, query.key)
                results[query.key] = MetricError(
                    metric_id=query.metric,
                    code="metric_failed",
                    message="This metric could not be computed.",
                )
        return MetricBatchResult(results=results)

    def _run_one(self, user_id: UUID, query: MetricQuery) -> MetricResult:
        spec = self._catalog.get(query.metric)
        if spec is None:
            raise MetricValidationError(
                "unknown_metric", f"Unknown metric '{query.metric}'."
            )

        query = normalize(spec, query)

        if spec.kind == "aggregation":
            return self._engine.execute(user_id, spec, query)

        resolver = self._resolvers.get(spec.id)
        if resolver is None:
            raise MetricValidationError(
                "resolver_missing",
                f"Metric '{spec.id}' is computed but no resolver is registered.",
            )
        return resolver.resolve(user_id, query, ResolverContext(spec=spec))


class GetMetricCatalogUseCase:
    """Exposes the catalog as data so the widget picker can enumerate it.

    This is the half a bespoke endpoint per metric has nowhere to put: declared
    params, units, shapes and unlock requirements, readable before any query.
    """

    def __init__(self, catalog: Mapping[str, MetricSpec] = METRIC_CATALOG) -> None:
        self._catalog = catalog

    def execute(self) -> list[MetricSpec]:
        return list(self._catalog.values())
