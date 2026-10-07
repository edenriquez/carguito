from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

#: Grid widths from docs/redesign-plan.md §4: sm=4 / md=6 / lg=12 columns.
#: Free 2-D resize was cut deliberately -- every chart would have to look right
#: at every aspect ratio and the payoff is decoration.
WIDGET_SIZES = ("sm", "md", "lg")


@dataclass(slots=True)
class DashboardWidget:
    """One metric placed on a dashboard.

    ``params`` holds the metric's own inputs (a projection's balance and rate);
    it is validated against the catalog on save, so a widget can never persist
    an ask the metric layer would later reject.
    """

    metric_id: str
    position: int
    size: str = "md"
    params: dict[str, Any] = field(default_factory=dict)
    title_override: str | None = None
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()


@dataclass(slots=True)
class Dashboard:
    """A user's composed grid of widgets."""

    user_id: UUID
    name: str = "Inicio"
    is_default: bool = True
    widgets: list[DashboardWidget] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()
        self.widgets.sort(key=lambda w: w.position)
