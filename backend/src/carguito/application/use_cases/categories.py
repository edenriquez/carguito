"""Grow the taxonomy by one leaf.

Reclasificación's Afinar field is a searchable select: an existing sibling
is a click, and a name nobody has used yet is Enter. The movement still
points at one id — this use case only mints the leaf so that id can exist.
"""

from __future__ import annotations

from uuid import UUID

from ...domain.entities import Category
from ...domain.services.categorization import normalize
from ..ports.outbound import CategoryRepository, CubeWriter
from .update_transaction import UnknownCategoryError

MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 120


class InvalidCategoryNameError(ValueError):
    """The name is empty, too short, or too long to put on a chip."""


class InvalidParentError(ValueError):
    """Afinar only grows a child under a root, never a grandchild."""


def _fold(name: str) -> str:
    return normalize(name)


class CreateCategoryUseCase:
    def __init__(self, *, categories: CategoryRepository, cube: CubeWriter) -> None:
        self._categories = categories
        self._cube = cube

    def execute(self, *, name: str, parent_id: UUID) -> Category:
        clean = " ".join(name.split())
        if len(clean) < MIN_NAME_LENGTH or len(clean) > MAX_NAME_LENGTH:
            raise InvalidCategoryNameError(
                f"Category name must be {MIN_NAME_LENGTH}–{MAX_NAME_LENGTH} characters"
            )

        catalog = self._categories.get_all()
        parent = next((c for c in catalog if c.id == parent_id), None)
        if parent is None:
            raise UnknownCategoryError(str(parent_id))
        if parent.parent_id is not None:
            raise InvalidParentError("A subcategory cannot have children")
        if _fold(parent.name) == _fold("Sin Categoria"):
            raise InvalidParentError("Sin Categoria cannot have children")

        folded = _fold(clean)
        if folded == _fold("Sin Categoria"):
            raise InvalidCategoryNameError("That name is reserved")

        for sibling in catalog:
            if sibling.parent_id == parent_id and _fold(sibling.name) == folded:
                return sibling

        child = Category(
            name=clean,
            color=parent.color,
            icon=parent.icon,
            categorization_labels=[],
            parent_id=parent.id,
        )
        self._categories.add_many([child])
        self._cube.sync_categories([child])
        return child
