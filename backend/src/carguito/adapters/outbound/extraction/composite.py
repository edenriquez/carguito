from __future__ import annotations

import logging

from ....application.dtos.extraction import ExtractedDocument
from .ocr import OcrPdfExtractor
from .pdf_text import NeedsOcrError, PdfTextExtractor

logger = logging.getLogger(__name__)


class PdfExtractor:
    """Extractor for PDFs that prefers the embedded text layer and falls back
    to OCR for scanned documents.

    Presents a single :class:`Extractor` to the pipeline; the text-vs-OCR
    decision is an internal detail of this adapter.
    """

    def __init__(
        self,
        text_extractor: PdfTextExtractor | None = None,
        ocr_extractor: OcrPdfExtractor | None = None,
    ) -> None:
        self._text = text_extractor or PdfTextExtractor()
        self._ocr = ocr_extractor or OcrPdfExtractor()

    def supports(self, filename: str, mime: str | None) -> bool:
        return filename.lower().endswith(".pdf")

    def extract(
        self,
        data: bytes,
        filename: str,
        mime: str | None,
        password: str | None = None,
    ) -> ExtractedDocument:
        try:
            return self._text.extract(data, filename, mime, password=password)
        except NeedsOcrError:
            logger.info("No text layer in %s; falling back to OCR", filename)
            # Reaching OCR means the text extractor already opened the file,
            # so a password that got this far is known-good.
            return self._ocr.extract(data, filename, mime, password=password)
