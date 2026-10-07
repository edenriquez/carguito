from __future__ import annotations

from ....application.dtos.extraction import ExtractedDocument


class SatXmlExtractor:
    """Loads SAT CFDI XML (Mexican digital invoices) as an XML document.

    Actual field parsing happens in the SAT CFDI parser; here we just surface
    the raw XML so the classifier can route it.
    """

    def supports(self, filename: str, mime: str | None) -> bool:
        name = filename.lower()
        return name.endswith(".xml") or (mime or "").endswith("xml")

    def extract(
        self,
        data: bytes,
        filename: str,
        mime: str | None,
        password: str | None = None,
    ) -> ExtractedDocument:
        # `password` is part of the Extractor contract for encrypted PDFs;
        # SAT XML has no such thing, so it is accepted and ignored.
        xml = data.decode("utf-8", errors="replace")
        return ExtractedDocument(kind="xml", filename=filename, xml=xml, mime=mime)
