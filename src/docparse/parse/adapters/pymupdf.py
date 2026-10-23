"""Native PDF content (text layer, images, vector graphics, simple tables) -> blocks. No confidence."""
import html

import pymupdf

from ..format import Block
from ..render import rect_to_pixels

DRAWING_GAP_PT = 6.0  # rectangles closer than this belong to one drawing
DRAWING_MIN_PT = 12.0  # smaller clusters (rules, bullets) are not reported
MAX_DRAWINGS = 200  # a page with more clusters is mostly hatching; keep the largest


def to_blocks(page: pymupdf.Page, to_pixels: pymupdf.Matrix) -> list[Block]:
    blocks: list[Block] = []
    table_rects: list[pymupdf.Rect] = []

    for table in page.find_tables().tables:
        rows = table.extract()
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
        text = "\n".join("".join(s["text"] for s in line["spans"]) for line in b["lines"]).strip()
        if text:
            blocks.append(Block(
                type="text", label="text", bbox=rect_to_pixels(rect, to_pixels), engine="pymupdf", text=text,
            ))

    for info in page.get_image_info():
        blocks.append(Block(type="image", label="image", bbox=rect_to_pixels(info["bbox"], to_pixels), engine="pymupdf"))

    for rect in _drawing_clusters(page):
        blocks.append(Block(type="drawing", label="drawing", bbox=rect_to_pixels(rect, to_pixels), engine="pymupdf"))

    for i, b in enumerate(blocks):
        b.order = i
    return blocks


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
