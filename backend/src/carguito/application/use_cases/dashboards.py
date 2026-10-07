from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from ...domain.entities import WIDGET_SIZES, Dashboard, DashboardWidget
from ...domain.metrics.catalog import METRIC_CATALOG
from ...domain.metrics.spec import MetricSpec, MetricValidationError
from ..ports.outbound import DashboardRepository

#: What a new user sees before composing anything: the three metrics that
#: actually work today (docs/redesign-plan.md §3). Accumulated spend is `lg`
#: because it is the one that answers "am I on track" at a glance and a
#: half-width version of it would be decoration.
STARTER_LAYOUT = (
    ("spend_by_category", "md"),
    ("monthly_cash_flow", "md"),
    ("accumulated_spend", "lg"),
)


def _starter_widgets() -> list[DashboardWidget]:
    return [
        DashboardWidget(metric_id=metric_id, position=index, size=size)
        for index, (metric_id, size) in enumerate(STARTER_LAYOUT)
    ]


class GetHomeDashboardUseCase:
    """Reads the user's home dashboard, creating a starter layout on first read.

    Lazily rather than at signup: there is no signup, and a dashboard created by
    a migration for a user who never arrives is a row that has to be kept in
    sync with a catalog that is still changing.
    """

    def __init__(self, dashboards: DashboardRepository) -> None:
        self._dashboards = dashboards

    def execute(self, *, user_id: UUID) -> Dashboard:
        existing = self._dashboards.get_default_for_user(user_id)
        if existing is not None:
            return existing

        dashboard = Dashboard(
            user_id=user_id, name="Inicio", is_default=True, widgets=_starter_widgets()
        )
        self._dashboards.add(dashboard)
        return dashboard


class SaveHomeDashboardUseCase:
    """Replaces the home dashboard's widget list, validated against the catalog.

    This is the point of doing B4 early: it forces every widget to be
    expressible as (metric id, params) drawn from the registry. A layout that
    could persist a metric name nobody implements, or params the metric would
    reject at query time, would turn a 400 at save into a permanently broken
    card at render.
    """

    def __init__(
        self,
        dashboards: DashboardRepository,
        catalog: Mapping[str, MetricSpec] = METRIC_CATALOG,
    ) -> None:
        self._dashboards = dashboards
        self._catalog = catalog

    def execute(self, *, user_id: UUID, widgets: Sequence[DashboardWidget]) -> Dashboard:
        # Validate the whole list before touching storage: a half-saved layout
        # is worse than a rejected one.
        validated = [self._validate(w, position) for position, w in enumerate(widgets)]

        dashboard = self._dashboards.get_default_for_user(user_id)
        if dashboard is None:
            dashboard = Dashboard(user_id=user_id, name="Inicio", is_default=True, widgets=[])
            self._dashboards.add(dashboard)

        self._dashboards.replace_widgets(dashboard.id, validated)
        dashboard.widgets = validated
        return dashboard

    def _validate(self, widget: DashboardWidget, position: int) -> DashboardWidget:
        spec = self._catalog.get(widget.metric_id)
        if spec is None:
            raise MetricValidationError(
                "unknown_metric",
                f"Unknown metric '{widget.metric_id}' at position {position}.",
            )
        if widget.size not in WIDGET_SIZES:
            raise MetricValidationError(
                "invalid_size",
                f"Widget size '{widget.size}' is not one of {list(WIDGET_SIZES)}.",
            )
        # Raises on an undeclared param, a missing required one, or a value out
        # of range -- the same check the query path runs, so a saved widget is
        # by construction a widget that can be queried.
        spec.coerce_params(widget.params)

        # Position is the array index, not a client-supplied number: two widgets
        # claiming position 3 is not a state worth being able to represent.
        return DashboardWidget(
            id=widget.id,
            metric_id=widget.metric_id,
            position=position,
            size=widget.size,
            params=dict(widget.params),
            title_override=widget.title_override,
        )
