"""Native PDF content (text layer, images, vector graphics, simple tables) -> blocks. No confidence."""
import html
import re

import pymupdf

from ..format import Block
from ..render import rect_to_pixels

DRAWING_GAP_PT = 6.0  # rectangles closer than this belong to one drawing
DRAWING_MIN_PT = 12.0  # smaller clusters (rules, bullets) are not reported
MAX_DRAWINGS = 200  # a page with more clusters is mostly hatching; keep the largest

# Some embedded/subset fonts map the micro-sign glyph to U+2026 (ellipsis) in their ToUnicode
# CMap instead of U+00B5 (observed in ds-tps62130: font "CALIBRI_02" renders a visible "µ" but
# pymupdf reports "…", e.g. "0.1 …F" where the PDF shows "0.1 µF"). pymupdf only reports what the
# font's own cmap says, so this is a PDF/font bug, not a pymupdf bug -- it cannot be fixed by
# reading the text layer differently, only detected and corrected after the fact. Scoped
# narrowly: only an ellipsis directly between a digit and a single unit letter (not the start of
# an ordinary word, hence the trailing negative lookahead) is remapped, since a literal ellipsis
# could never legitimately appear in that exact position (a one-letter unit suffix).
_MICRO_SIGN_MANGLE_RE = re.compile(r"(?<=[0-9])(\s?)…(?=[A-Za-zΩ](?![A-Za-z]))")


def _fix_micro_sign_mangling(text: str) -> str:
    return _MICRO_SIGN_MANGLE_RE.sub(r"\1µ", text)


def to_blocks(page: pymupdf.Page, to_pixels: pymupdf.Matrix) -> list[Block]:
    """Blocks of one page; boxes are clipped to the page image (scans and drawings often reach beyond the page); blocks outside the page are dropped."""
    bounds = pymupdf.Rect(page.rect) * page.derotation_matrix * to_pixels  # page.rect is rotated, block coordinates are not
    bounds.normalize()
    blocks: list[Block] = []
    table_rects: list[pymupdf.Rect] = []

    for table in page.find_tables().tables:
        rows = [[_fix_micro_sign_mangling(c) if c else c for c in row] for row in table.extract()]
        table_rects.append(pymupdf.Rect(table.bbox))
        blocks.append(Block(
            type="table", label="table", bbox=rect_to_pixels(table.bbox, to_pixels), engine="pymupdf",
            html=_rows_to_html(rows), text="\n".join("\t".join(c or "" for c in r) for r in rows),
        ))

    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        rect = pymupdf.Rect(b["bbox"])
        if any(rect.intersects(t) and (rect & t).get_area() > 0.5 * rect.get_area() for t in table_rects):
            continue  # already part of a table
        text = _fix_micro_sign_mangling(
            "\n".join("".join(s["text"] for s in line["spans"]) for line in b["lines"]).strip()
        )
        if text:
            blocks.append(Block(
                type="text", label="text", bbox=rect_to_pixels(rect, to_pixels), engine="pymupdf", text=text,
            ))

    for info in page.get_image_info():
        blocks.append(Block(type="image", label="image", bbox=rect_to_pixels(info["bbox"], to_pixels), engine="pymupdf"))

    for rect in _drawing_clusters(page):
        blocks.append(Block(type="drawing", label="drawing", bbox=rect_to_pixels(rect, to_pixels), engine="pymupdf"))

    visible = []
    for b in blocks:
        b.bbox = [max(b.bbox[0], bounds.x0), max(b.bbox[1], bounds.y0), min(b.bbox[2], bounds.x1), min(b.bbox[3], bounds.y1)]
        if b.bbox[0] <= b.bbox[2] and b.bbox[1] <= b.bbox[3]:  # blocks entirely off the page are dropped
            b.order = len(visible)
            visible.append(b)
    return visible


def _rows_to_html(rows: list[list[str | None]]) -> str:
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c or '')}</td>" for c in row) + "</tr>" for row in rows
    )
    return f"<table>{body}</table>"


def _drawing_clusters(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """Group vector paths whose boxes (grown by DRAWING_GAP_PT) overlap into one rectangle each."""
    rects = [pymupdf.Rect(d["rect"]) for d in page.get_drawings() if d.get("rect") is not None]
    rects = [r for r in rects if not r.is_empty or r.width > 0 or r.height > 0]
    parent = list(range(len(rects)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cell = 4 * DRAWING_GAP_PT
    grid: dict[tuple[int, int], list[int]] = {}
    grown = [pymupdf.Rect(r.x0 - DRAWING_GAP_PT, r.y0 - DRAWING_GAP_PT, r.x1 + DRAWING_GAP_PT, r.y1 + DRAWING_GAP_PT) for r in rects]
    for i, g in enumerate(grown):
        for cx in range(int(g.x0 // cell), int(g.x1 // cell) + 1):
            for cy in range(int(g.y0 // cell), int(g.y1 // cell) + 1):
                for j in grid.setdefault((cx, cy), []):
                    if grown[i].intersects(grown[j]):
                        parent[find(i)] = find(j)
                grid[(cx, cy)].append(i)

    clusters: dict[int, pymupdf.Rect] = {}
    for i, r in enumerate(rects):
        root = find(i)
        clusters[root] = clusters[root] | r if root in clusters else pymupdf.Rect(r)
    big = [c for c in clusters.values() if c.width >= DRAWING_MIN_PT or c.height >= DRAWING_MIN_PT]
    big.sort(key=lambda c: c.get_area(), reverse=True)
    return sorted(big[:MAX_DRAWINGS], key=lambda c: (c.y0, c.x0))
