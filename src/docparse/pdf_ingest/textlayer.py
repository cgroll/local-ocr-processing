"""Text layer of a PDF as `pymupdf` PageResults, plus heading levels from font sizes.

The generic `pymupdf` adapter reports blocks without font information. Here the same blocks are
produced, then text blocks that are clearly larger (or short and bold) than the body text are
marked `type="title"` with `label="h1".."h3"`, which the Markdown assembly renders as headings.
"""
import re
from collections import Counter

import pymupdf

from ..parse.adapters import pymupdf as adapter
from ..parse.format import Block, PageResult
from ..parse.render import rect_to_pixels

DPI = 150
HEADING_RATIO = 1.15  # span size / body size from which a block is a heading
MAX_HEADING_CHARS = 250
MAX_HEADING_LINES = 4
MAX_HEADING_SHARE = 0.4  # more headings than this share of a page's blocks: not trusted
SAMPLE_PAGES = 120  # pages looked at to find the body font size
MIN_SCAN_CHARS = 20  # fewer characters than this (plus an image) = scanned page

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_INVISIBLE = dict.fromkeys(map(ord, "­​‌‍﻿"))


def clean_text(text: str) -> str:
    """Ligatures to letters, soft hyphens and zero-width characters removed (not NFKC: that would turn
    the micro sign into a Greek mu and break searches for units)."""
    for lig, plain in LIGATURES.items():
        text = text.replace(lig, plain)
    return text.translate(_INVISIBLE)


def page_geometry(page: pymupdf.Page, dpi: int = DPI) -> tuple[pymupdf.Matrix, int, int]:
    """Matrix from PDF points to image pixels (as `parse.render` does) and the image size."""
    scale = pymupdf.Matrix(dpi / 72, dpi / 72)
    rect = pymupdf.Rect(page.rect) * scale
    return page.rotation_matrix * scale, max(1, round(rect.width)), max(1, round(rect.height))


def _spans(page: pymupdf.Page):
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        yield b


def body_font_size(doc: pymupdf.Document) -> float:
    """Most common font size by characters, over an even sample of pages; 0 when there is no text."""
    counts: Counter = Counter()
    step = max(1, len(doc) // SAMPLE_PAGES)
    for i in range(0, len(doc), step):
        for b in _spans(doc[i]):
            for line in b["lines"]:
                for s in line["spans"]:
                    n = len(s["text"].strip())
                    if n:
                        counts[round(s["size"] * 2) / 2] += n
    return counts.most_common(1)[0][0] if counts else 0.0


def heading_sizes(doc: pymupdf.Document, body: float) -> list[float]:
    """Distinct heading sizes, largest first (at most three levels)."""
    if not body:
        return []
    counts: Counter = Counter()
    step = max(1, len(doc) // SAMPLE_PAGES)
    for i in range(0, len(doc), step):
        for b in _spans(doc[i]):
            size = max((s["size"] for line in b["lines"] for s in line["spans"] if s["text"].strip()), default=0)
            if size >= body * HEADING_RATIO:
                counts[round(size * 2) / 2] += 1
    sizes = sorted(counts, reverse=True)
    # merge sizes that differ by less than 1 pt into the larger one
    merged: list[float] = []
    for s in sizes:
        if not merged or merged[-1] - s >= 1.0:
            merged.append(s)
    return merged[:3]


def _style(b: dict) -> tuple[float, bool, int, int]:
    """(max size, all bold, characters, lines) of one text block of `get_text("dict")`."""
    size, bold, chars = 0.0, True, 0
    for line in b["lines"]:
        for s in line["spans"]:
            t = s["text"].strip()
            if not t:
                continue
            chars += len(t)
            size = max(size, s["size"])
            if not (s["flags"] & 16 or "bold" in s["font"].lower()):
                bold = False
    return size, bold and chars > 0, chars, len(b["lines"])


def _iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda r: max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])  # noqa: E731
    union = area(a) + area(b) - ix
    return ix / union if union > 0 else 0.0


def _heading_level(size: float, bold: bool, chars: int, lines: int, text: str, body: float, levels: list[float]) -> int | None:
    if not body or chars > MAX_HEADING_CHARS or lines > MAX_HEADING_LINES:
        return None
    if size >= body * HEADING_RATIO and levels:
        return 1 + min(range(len(levels)), key=lambda i: abs(levels[i] - size))
    if text.rstrip().endswith(("-", ",", ";")) or not any(c.isalpha() for c in text):
        return None  # a line of running text or a number, not a heading
    if bold and size >= body * 0.97 and chars <= 100 and not text.rstrip().endswith((".", ":")):
        return 3
    return None


def extract_page(doc: pymupdf.Document, index: int, doc_id: str, body: float, levels: list[float], dpi: int = DPI) -> PageResult:
    """Blocks of one page (0-based `index`) as a `pymupdf` PageResult with headings marked."""
    page = doc[index]
    to_pixels, width, height = page_geometry(page, dpi)
    blocks = adapter.to_blocks(page, to_pixels)
    styles = [(rect_to_pixels(b["bbox"], to_pixels), _style(b)) for b in _spans(page)]
    for blk in blocks:
        if blk.type != "text" or not blk.text:
            continue
        best = max(styles, key=lambda s: _iou(blk.bbox, s[0]), default=None)
        if best is None or _iou(blk.bbox, best[0]) < 0.5:
            continue
        size, bold, chars, lines = best[1]
        level = _heading_level(size, bold, chars, lines, blk.text, body, levels)
        if level is not None:
            blk.type, blk.label = "title", f"h{level}"
    # a page that is mostly "headings" has an OCR text layer with odd font sizes: no headings there
    texts = [b for b in blocks if b.type in ("text", "title") and b.text]
    titles = [b for b in texts if b.type == "title"]
    if len(titles) > max(6, MAX_HEADING_SHARE * len(texts)):
        for b in titles:
            b.type, b.label = "text", "text"
    return PageResult(doc_id, index + 1, dpi, width, height, "pymupdf", pymupdf.__version__, blocks=blocks)


def is_scan(page: pymupdf.Page) -> bool:
    """No usable text layer but an image on the page."""
    return len(page.get_text().strip()) < MIN_SCAN_CHARS and bool(page.get_images(full=False))


_BOUND = re.compile(r"\s+")


def plain(text: str) -> str:
    return _BOUND.sub(" ", clean_text(text)).strip()
