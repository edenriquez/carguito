from __future__ import annotations

import io

from ....application.dtos.extraction import ExtractedDocument
from ....application.ports.outbound import PdfPasswordError


class PdfTextExtractor:
    """Extracts embedded text from digital PDFs using pdfplumber.

    This is the fast path for statements that already contain a text layer
    (most bank e-statements). Scanned/image PDFs yield little text and should
    fall through to :class:`OcrPdfExtractor`.
    """

    MIN_TEXT_CHARS = 40

    def supports(self, filename: str, mime: str | None) -> bool:
        return filename.lower().endswith(".pdf")

    def extract(
        self,
        data: bytes,
        filename: str,
        mime: str | None,
        password: str | None = None,
    ) -> ExtractedDocument:
        import pdfplumber

        lines: list[str] = []
        try:
            with pdfplumber.open(io.BytesIO(data), password=password or "") as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    lines.extend(ln for ln in text.splitlines() if ln.strip())
        except Exception as exc:
            if _is_password_failure(exc):
                # Same open, two meanings: with no password this is the first
                # ask, with one it is a rejection the client should retry.
                raise PdfPasswordError(
                    filename, "incorrect" if password else "required"
                ) from exc
            raise

        joined = "\n".join(lines)
        if len(joined) < self.MIN_TEXT_CHARS:
            # Signal to the pipeline that OCR is required.
            raise NeedsOcrError(filename)
        return ExtractedDocument(
            kind="text", filename=filename, text=joined, lines=lines, mime=mime
        )


def _is_password_failure(exc: Exception) -> bool:
    """True when the exception means "wrong or missing password".

    pdfplumber 0.11 wraps pdfminer's ``PDFPasswordIncorrect`` in its own
    ``PdfminerException`` with the original as ``args[0]`` (not ``__cause__``),
    so both the wrapped and the bare form are checked.
    """
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    if isinstance(exc, PDFPasswordIncorrect):
        return True
    return any(isinstance(arg, PDFPasswordIncorrect) for arg in exc.args)


class NeedsOcrError(Exception):
    """Raised when a PDF has no usable text layer and needs OCR."""
