from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from nacl.exceptions import CryptoError
from nacl.public import Box, PrivateKey, PublicKey

logger = logging.getLogger(__name__)

#: What the phone must implement. Published in ``GET /api/ingest/key`` so the
#: client never has to guess, and so a future rotation to a different primitive
#: is a value change rather than a protocol break.
ALGORITHM = "x25519-xsalsa20-poly1305"

_PUBLIC_KEY_BYTES = 32
_NONCE_BYTES = 24
_KEY_ID_HEX_CHARS = 12
_FILE_VERSION = 1


class SealedEnvelopeError(Exception):
    """The envelope could not be opened.

    Deliberately one error for every failure mode -- unknown key, malformed
    base64, wrong length, forged tag. The caller answers 400 either way, and
    distinguishing them in the response would tell an attacker which half of
    their guess was right.
    """


@dataclass(frozen=True)
class IngestKey:
    """One server keypair, as it lives on disk and on the wire."""

    key_id: str
    public_key: bytes
    private_key: PrivateKey
    created_at: str

    @property
    def public_key_b64(self) -> str:
        return base64.b64encode(self.public_key).decode("ascii")


def key_id_for(public_key: bytes) -> str:
    """First 12 hex chars of ``sha256`` over the raw 32 public-key bytes.

    Over the *bytes*, not their base64 spelling: the identifier names the key,
    so re-encoding it (padding, urlsafe alphabet) must not rename it.
    """
    return hashlib.sha256(public_key).hexdigest()[:_KEY_ID_HEX_CHARS]


class FileIngestKeyring:
    """The server's X25519 identity for device ingest, persisted outside git.

    Generated on first bootstrap rather than configured: a keypair nobody had
    to mint by hand is a keypair that exists in every environment, and the
    public half is discoverable at ``GET /api/ingest/key`` anyway. The file is
    written 0600 and gitignored -- leaking the secret half would undo the whole
    point of the sealed envelope (docs/custody-plan.md G3).

    Stored as a **list, newest first**, so rotation is later a matter of
    prepending a key and letting old phones keep sending under the old
    ``key_id`` until they re-pin. Only one key is ever minted today; the shape
    is what costs nothing now and everything to retrofit.
    """

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._keys: list[IngestKey] | None = None

    # --- lifecycle -------------------------------------------------------
    def ensure(self) -> IngestKey:
        """Load the keyring, minting one if this is the first boot."""
        return self.current

    @property
    def keys(self) -> list[IngestKey]:
        if self._keys is None:
            self._keys = self._load() or self._create()
        return self._keys

    @property
    def current(self) -> IngestKey:
        """The key new clients should seal to: newest first."""
        return self.keys[0]

    def find(self, key_id: str) -> IngestKey | None:
        return next((k for k in self.keys if k.key_id == key_id), None)

    # --- the one operation the HTTP layer needs --------------------------
    def open_envelope(self, *, key_id: str, epk: str, nonce: str, box: str) -> bytes:
        """Decrypt a ``crypto_box`` envelope in memory and return the plaintext.

        The sender is an *ephemeral* key the phone throws away after the
        request, so the box authenticates the message without identifying the
        device -- and the plaintext exists only as the return value of this
        call, never as a file.
        """
        key = self.find(key_id)
        if key is None:
            raise SealedEnvelopeError(f"Unknown key_id {key_id!r}")

        sender = _decode(epk, "epk", expected_len=_PUBLIC_KEY_BYTES)
        nonce_bytes = _decode(nonce, "nonce", expected_len=_NONCE_BYTES)
        ciphertext = _decode(box, "box")
        try:
            return Box(key.private_key, PublicKey(sender)).decrypt(ciphertext, nonce_bytes)
        except (CryptoError, ValueError) as exc:
            # No plaintext, no key material, no ciphertext in the log line: the
            # only safe thing to say is that it did not open.
            logger.warning("ingest: envelope for key_id=%s failed to open", key_id)
            raise SealedEnvelopeError("Envelope could not be decrypted") from exc

    # --- persistence -----------------------------------------------------
    def _load(self) -> list[IngestKey] | None:
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text("utf-8"))
            entries = raw["keys"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Refuse to silently mint a replacement: a corrupt keyring means
            # every pinned phone is about to be told the server changed
            # identity, which is precisely the alarm TOFU exists to raise.
            raise RuntimeError(f"Unreadable ingest keyring at {self._path}: {exc}") from exc
        return [
            IngestKey(
                key_id=entry["key_id"],
                public_key=base64.b64decode(entry["public_key"]),
                private_key=PrivateKey(base64.b64decode(entry["private_key"])),
                created_at=entry.get("created_at", ""),
            )
            for entry in entries
        ]

    def _create(self) -> list[IngestKey]:
        private = PrivateKey.generate()
        public = bytes(private.public_key)
        key = IngestKey(
            key_id=key_id_for(public),
            public_key=public,
            private_key=private,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._write([key])
        logger.info("ingest: minted keypair key_id=%s at %s", key.key_id, self._path)
        # Re-read rather than trust what we just wrote: two workers booting at
        # once both mint, and only one file survives the rename. Whoever loses
        # must adopt the winner's key or it would hand out a public key it
        # cannot decrypt against.
        return self._load() or [key]

    def _write(self, keys: list[IngestKey]) -> None:
        document = {
            "v": _FILE_VERSION,
            "algorithm": ALGORITHM,
            "keys": [
                {
                    "key_id": k.key_id,
                    "public_key": k.public_key_b64,
                    "private_key": base64.b64encode(bytes(k.private_key)).decode("ascii"),
                    "created_at": k.created_at,
                }
                for k in keys
            ],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Written to a sibling temp file and renamed: a half-written keyring is
        # a server that cannot decrypt anything, and 0600 from birth means the
        # secret is never briefly world-readable.
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), prefix=".ingest_key-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(document, fh, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _decode(value: object, field: str, *, expected_len: int | None = None) -> bytes:
    """Base64 -> bytes, forgiving about spelling and strict about length.

    Padding and the urlsafe alphabet are accepted because libsodium bindings
    disagree about both across platforms, and rejecting a correctly encrypted
    payload over a ``-`` would be a debugging afternoon for no security gain.
    """
    if not isinstance(value, str) or not value.strip():
        raise SealedEnvelopeError(f"'{field}' must be a non-empty base64 string")
    text = value.strip().replace("-", "+").replace("_", "/")
    text += "=" * (-len(text) % 4)
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SealedEnvelopeError(f"'{field}' is not valid base64") from exc
    if expected_len is not None and len(raw) != expected_len:
        raise SealedEnvelopeError(f"'{field}' must be {expected_len} bytes, got {len(raw)}")
    return raw
