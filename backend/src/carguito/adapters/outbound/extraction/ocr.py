from __future__ import annotations

from ....application.dtos.extraction import ExtractedDocument


class OcrPdfExtractor:
    """OCR fallback for scanned/image PDFs using Tesseract.

    Requires the optional ``ocr`` extra (``pytesseract``, ``pdf2image``,
    ``pillow``) plus a system Tesseract + poppler install. Imports are lazy so
    the backend runs without these heavy dependencies when only digital PDFs
    and SAT XML are used.
    """

    def __init__(self, lang: str = "spa+eng", dpi: int = 300) -> None:
        self._lang = lang
        self._dpi = dpi

    def supports(self, filename: str, mime: str | None) -> bool:
        # Registered as an explicit fallback; the pipeline invokes it directly
        # when text extraction is insufficient, so it does not auto-claim files.
        return False

    def extract(
        self,
        data: bytes,
        filename: str,
        mime: str | None,
        password: str | None = None,
    ) -> ExtractedDocument:
        try:
            import pytesseract
            from pdf2image import convert_from_bytes
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "OCR support requires the 'ocr' extra: pip install '.[ocr]'"
            ) from exc

        lines: list[str] = []
        for image in convert_from_bytes(data, dpi=self._dpi, userpw=password or None):
            text = pytesseract.image_to_string(image, lang=self._lang)
            lines.extend(ln for ln in text.splitlines() if ln.strip())

        joined = "\n".join(lines)
        return ExtractedDocument(
            kind="text", filename=filename, text=joined, lines=lines, mime=mime
        )
