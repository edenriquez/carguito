"""Display aliases: the user's names for processor gibberish.

"POCK*SUPERLECLERC MX" is a grocery store near the user's home. The alias
service rewrites a transaction's *description* — the editable, human-facing
label — while ``raw_description`` keeps the bank's original text, so the
evidence never degrades and the alias is always reversible.
"""

from __future__ import annotations

from .categorization import normalize


class AliasService:
    """Longest-label-first matching, same discipline as categorization:
    "superleclerc polanco" must win over "superleclerc" when both are taught.
    """

    def __init__(self, aliases: list[tuple[str, str]]) -> None:
        """`aliases` are (normalized label, display alias) pairs."""
        self._index = sorted(
            ((label, alias) for label, alias in aliases if label),
            key=lambda p: len(p[0]),
            reverse=True,
        )

    def match(self, raw_description: str) -> tuple[str, str] | None:
        """The (label, alias) pair that matches, or None.

        The label matters to callers that key on identity — the recurrence
        detector groups by it — while display-only callers use `apply`.
        """
        norm = normalize(raw_description)
        for label, alias in self._index:
            if label in norm:
                return (label, alias)
        return None

    def apply(self, raw_description: str) -> str | None:
        """The alias for a description, or None when nothing matches."""
        matched = self.match(raw_description)
        return matched[1] if matched else None
