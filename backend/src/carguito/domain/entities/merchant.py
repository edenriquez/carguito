from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(slots=True)
class Merchant:
    name: str
    labels: list[str] = field(default_factory=list)
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()
