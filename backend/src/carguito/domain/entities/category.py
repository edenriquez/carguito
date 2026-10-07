from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(slots=True)
class Category:
    name: str
    color: str | None = None
    icon: str | None = None
    categorization_labels: list[str] = field(default_factory=list)
    # Null = root. One level: a child never has children.
    parent_id: UUID | None = None
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()
