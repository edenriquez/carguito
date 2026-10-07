from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class FileStorage(Protocol):
    """Transient storage for raw uploads.

    Raw files are only held while a statement is being processed and MUST be
    discarded afterwards; nothing here is a durable store.
    """

    def save(self, data: bytes, filename: str) -> str:
        """Persist bytes transiently and return an opaque handle/path."""

    def read(self, handle: str) -> bytes: ...

    def discard(self, handle: str) -> None:
        """Delete the transient file. Safe to call more than once."""
