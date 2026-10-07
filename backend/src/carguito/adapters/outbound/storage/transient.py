from __future__ import annotations

import os
import tempfile
import uuid


class TransientFileStorage:
    """Stores uploads in a temp directory only for the duration of processing.

    Implements the :class:`FileStorage` port. Files are expected to be
    ``discard``-ed by the caller as soon as parsing completes so that raw
    statements never persist server-side.
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = base_dir or os.path.join(tempfile.gettempdir(), "tomin_transient")
        os.makedirs(self._base, exist_ok=True)

    def save(self, data: bytes, filename: str) -> str:
        handle = os.path.join(self._base, f"{uuid.uuid4().hex}_{os.path.basename(filename)}")
        with open(handle, "wb") as fh:
            fh.write(data)
        return handle

    def read(self, handle: str) -> bytes:
        with open(handle, "rb") as fh:
            return fh.read()

    def discard(self, handle: str) -> None:
        try:
            os.remove(handle)
        except FileNotFoundError:
            pass
