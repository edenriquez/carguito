from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from ..entities.category import Category
from ..entities.merchant import Merchant

_WS = re.compile(r"\s+")
_NOISE = re.compile(r"[^a-z0-9 ]+")


def normalize(text: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace.

    Used both to normalize merchant labels and incoming transaction
    descriptions so that matching is robust to bank formatting noise.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = _NOISE.sub(" ", text)
    return _WS.sub(" ", text).strip()


@dataclass(frozen=True)
class Classification:
    category_id: UUID | None
    merchant_id: UUID | None


class CategorizationService:
    """Assigns a category and merchant to a transaction description.

    Pure domain logic: it receives the reference data (categories, merchants)
    and performs longest-label matching against a normalized description.
    """

    def __init__(
        self,
        categories: list[Category],
        merchants: list[Merchant],
        extra_labels: Iterable[tuple[str, UUID]] = (),
    ) -> None:
        """`extra_labels` is the user's own learned vocabulary — (label,
        category_id) pairs taught through corrections. Merged into the same
        index as the global labels so specificity (longest-first) decides
        between them, not provenance."""
        self._categories = categories
        self._merchants = merchants
        # Pre-compute normalized (label -> id), longest labels first for specificity.
        self._cat_index = self._build_index(
            [(lbl, c.id) for c in categories for lbl in c.categorization_labels]
            + list(extra_labels)
        )
        self._merchant_index = self._build_index(
            (lbl, m.id) for m in merchants for lbl in ([m.name] + m.labels)
        )
        self._fallback_category = next(
            (c.id for c in categories if normalize(c.name) == normalize("Sin Categoria")),
            None,
        )

    @staticmethod
    def _build_index(pairs) -> list[tuple[str, UUID]]:
        index = [(normalize(lbl), _id) for lbl, _id in pairs if normalize(lbl)]
        index.sort(key=lambda p: len(p[0]), reverse=True)
        return index

    def classify(self, raw_description: str) -> Classification:
        norm = normalize(raw_description)
        merchant_id = self._match(norm, self._merchant_index)
        category_id = self._match(norm, self._cat_index) or self._fallback_category
        return Classification(category_id=category_id, merchant_id=merchant_id)

    @staticmethod
    def _match(norm: str, index: list[tuple[str, UUID]]) -> UUID | None:
        for label, _id in index:
            if not label:
                continue
            # Short labels ("gas") are words, not substrings: otherwise
            # "recargas" files under the gas bill.
            if len(label) <= 3:
                if re.search(rf"(^| ){re.escape(label)}( |$)", norm):
                    return _id
            elif label in norm:
                return _id
        return None
