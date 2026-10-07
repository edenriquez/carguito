from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

#: ``plain`` is a label. ``investment`` marks a group whose totals are
#: *contributions*, not market value -- the distinction the plan is emphatic
#: about (docs/redesign-plan.md §3, metric 5): tagged outflows give you what you
#: put in, and calling that a return would be a lie. The kind exists so the UI
#: can label it honestly rather than inferring intent from a tag name.
TagKind = Literal["plain", "investment"]

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """A stable, comparable key for a tag name.

    Accents are folded rather than dropped, so ``Jubilación`` and ``jubilacion``
    collide instead of quietly becoming two tags that look identical in a list.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = _NON_SLUG.sub("-", folded.lower()).strip("-")
    if not slug:
        raise ValueError(f"Tag name {name!r} has no sluggable characters.")
    return slug


@dataclass(slots=True)
class Tag:
    """A user-defined label. Many per transaction, by design.

    Tags overlap: a transaction can be both ``viaje`` and ``deducible``, which
    is exactly why totals broken down by tag do not partition the total. That
    property is carried to the client as ``meta.overlapping``.
    """

    user_id: UUID
    name: str
    slug: str | None = None
    color: str | None = None
    kind: TagKind = "plain"
    created_at: datetime | None = None
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Tag name must not be empty.")
        if self.kind not in ("plain", "investment"):
            raise ValueError(f"Unknown tag kind {self.kind!r}; expected 'plain' or 'investment'.")
        if not self.slug:
            self.slug = slugify(self.name)
