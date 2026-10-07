"""Reading a ticket photo on the server with RapidOCR.

RapidOCR is PaddleOCR's detector + recognizer exported to ONNX and run on
the CPU through onnxruntime: a model trained on photographs, not scans, which
is the whole difference on thermal paper. Measured on the same five tickets
Tesseract read a third of, it reads the barcode, the name and the price of
nearly every row, and the ``28/09/26  14:32`` at the foot.

The dependency is optional (``pip install '.[receipts]'``) and imported
lazily: the models are a couple hundred megabytes of wheels nobody who only
uploads statements should install. Without it the container has no OCR and
the upload endpoint says so.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass

from ....application.ports.outbound import UnreadableImageError

logger = logging.getLogger(__name__)

#: Longest side the photo is scaled to before detection. A 12-megapixel
#: photo is more than the detector wants; at 2000px a ticket filling the
#: frame has 25px print, which the recognizer reads cleanly in ~1.5s.
MAX_SIDE = 2000

#: How much of a row's height two boxes' centres may differ by and still be
#: the same printed row. Half a row is the natural cut; past that the boxes
#: are stacked, not side by side. The rule the phone applies to ML Kit's
#: boxes (``mobile/src/lib/receipt-lines.ts``).
ROW_TOLERANCE_RATIO = 0.5

#: Enough money rows to call a read good and stop turning the photo.
GOOD_READ = 3

_MONEY = re.compile(r"\d+[.,]\d{2}")


@dataclass(frozen=True)
class _Box:
    text: str
    top: float
    left: float
    height: float

    @property
    def centre(self) -> float:
        return self.top + self.height / 2


def group_rows(boxes: list[_Box]) -> list[str]:
    """Boxes back into the rows the printer made.

    A detector returns *boxes*, and on a two-column thermal print the product
    name and its price are two boxes on the same physical row. Handed to the
    reader as-is, ``LECHE LALA ENT 1L`` and ``28.50`` arrive as separate lines
    and the reader (whose one rule is "a product line ends in money") sees a
    product with no price and a price with no product. So boxes are re-joined
    by vertical position, with a tolerance relative to the text's own height:
    a photo taken from 20 cm has rows three times taller than one from 60.
    """
    usable = sorted((b for b in boxes if b.text.strip()), key=lambda b: (b.top, b.left))
    rows: list[str] = []
    current: list[_Box] = []

    def flush() -> None:
        if not current:
            return
        text = " ".join(b.text.strip() for b in sorted(current, key=lambda b: b.left))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            rows.append(text)
        current.clear()

    for box in usable:
        if current:
            anchor = current[0]
            slack = max(anchor.height, box.height, 1.0) * ROW_TOLERANCE_RATIO
            if abs(box.centre - anchor.centre) > slack:
                flush()
        current.append(box)
    flush()
    return rows


def ticketness(rows: list[str]) -> int:
    """How much a read looks like a ticket: rows carrying money."""
    return sum(1 for row in rows if _MONEY.search(row))


class RapidOcrReceiptOcr:
    """Implements :class:`ReceiptImageOcr` over ``rapidocr_onnxruntime``."""

    label = "rapidocr-server"

    def __init__(self) -> None:
        self._engine = None

    @staticmethod
    def available() -> bool:
        try:
            import rapidocr_onnxruntime  # noqa: F401
            import PIL  # noqa: F401
        except ImportError:
            return False
        return True

    def _get_engine(self):
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            # Models load on first use (~1s) and stay loaded for the process.
            # The detector's box threshold is lowered from 0.5: on crumpled
            # thermal paper the faint names score just under it while their
            # prices score high, and a price with no name is a dropped row.
            # Measured on five real tickets; larger inputs and looser
            # pixel thresholds bought nothing more.
            self._engine = RapidOCR(det_box_thresh=0.4)
        return self._engine

    def read(self, image: bytes) -> list[str]:
        from PIL import Image, ImageOps, UnidentifiedImageError

        try:
            photo = Image.open(io.BytesIO(image))
            # The camera's note on which way is up, applied: without it every
            # portrait ticket arrives lying on its side.
            photo = ImageOps.exif_transpose(photo).convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise UnreadableImageError(str(exc)) from exc

        scale = min(1.0, MAX_SIDE / max(photo.size))
        if scale < 1.0:
            photo = photo.resize(
                (round(photo.width * scale), round(photo.height * scale)), Image.LANCZOS
            )

        # A ticket is taller than it is wide, so a landscape photo is almost
        # always one lying sideways and starts with a quarter turn; the read
        # is retried at the other angles when it comes back thin.
        landscape = photo.width > photo.height
        angles = (90, 270, 0, 180) if landscape else (0, 90, 270, 180)
        best: tuple[int, list[str]] | None = None
        for angle in angles:
            rows = self._recognize(photo.rotate(angle, expand=True) if angle else photo)
            score = ticketness(rows)
            if best is None or score > best[0]:
                best = (score, rows)
            if score >= GOOD_READ:
                break
        logger.info("receipt ocr: %d row(s), %d with money", len(best[1]), best[0])
        return best[1]

    def _recognize(self, photo) -> list[str]:
        import numpy as np

        result, _elapsed = self._get_engine()(np.asarray(photo))
        boxes: list[_Box] = []
        for quad, text, _score in result or []:
            xs = [float(p[0]) for p in quad]
            ys = [float(p[1]) for p in quad]
            boxes.append(
                _Box(text=str(text), top=min(ys), left=min(xs), height=max(ys) - min(ys))
            )
        return group_rows(boxes)
