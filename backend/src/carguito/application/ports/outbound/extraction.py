from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...dtos.extraction import ExtractedDocument, ParsedStatement


class PdfPasswordError(Exception):
    """An encrypted PDF could not be opened with the password on hand.

    ``reason`` distinguishes the first ask from a retry: ``"required"`` means
    no password was supplied, ``"incorrect"`` means one was and the PDF
    rejected it. Defined next to the port because it is part of the extraction
    contract — the HTTP layer maps it to a response the client can act on.
    """

    def __init__(self, filename: str, reason: str) -> None:
        super().__init__(filename)
        self.reason = reason  # "required" | "incorrect"


@runtime_checkable
class Extractor(Protocol):
    """Turns raw uploaded bytes into an :class:`ExtractedDocument`."""

    def supports(self, filename: str, mime: str | None) -> bool: ...

    def extract(
        self,
        data: bytes,
        filename: str,
        mime: str | None,
        password: str | None = None,
    ) -> ExtractedDocument: ...


@runtime_checkable
class TemplateClassifier(Protocol):
    """Identifies which parser template an extracted document belongs to.

    Returns a template key such as ``"banamex"``, ``"sat_cfdi"`` or
    ``"unknown"``.
    """

    def classify(self, doc: ExtractedDocument) -> str: ...

    def detect_bank(self, doc: ExtractedDocument) -> str | None:
        """The issuing bank's display name, independent of the template.

        Separate from :meth:`classify` because most banks have no dedicated
        parser — their statements parse as ``generic_bank`` — but the
        statement should still be labelled with the right bank.
        """
        ...


@runtime_checkable
class StatementParser(Protocol):
    """Parses an extracted document of a known template into a statement."""

    template_key: str

    def parse(self, doc: ExtractedDocument) -> ParsedStatement: ...


@runtime_checkable
class ParserFactory(Protocol):
    def get(self, template_key: str) -> StatementParser: ...
