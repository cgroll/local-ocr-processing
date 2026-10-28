"""Pure rendering helpers: engine blocks -> Markdown. No model calls, no I/O -- see `page.py`/
`document.py` for assembling a page/document from these."""
from html.parser import HTMLParser

from ..parse.format import Block

TABLE_STRUCTURE_WARNING = (
    "*Hinweis: automatisch aus HTML konvertiert, Zeilen-/Spaltenzuordnung unverifiziert "
    "(siehe `experiments/vlm-qa-test/README.md`, Follow-up A -- bekannte Schwäche bei "
    "mehreren Werten in einer Zelle).*"
)
RAW_FRAGMENTS_LABEL = (
    "**Erkannte Textfragmente in diesem Bereich (pymupdf/OCR, unverifiziert, keine Struktur):**"
)


def render_narrative_block(block: Block) -> str:
    """One non-visual block (title/header/footer/text/list/caption/...) as Markdown."""
    text = (block.text or block.markdown or "").strip()
    if not text:
        return ""
    if block.type == "title":
        return f"### {text}"
    if block.type == "caption":
        return f"*{text}*"
    if block.type == "list":
        return "\n".join(f"- {line}" for line in text.splitlines() if line.strip())
    return text


class _TableGridParser(HTMLParser):
    """Builds a dense grid from <table><tr><td rowspan=.. colspan=..>: spanned cells repeat
    their value into every cell they cover -- Markdown has no merged-cell syntax, and repeating
    is the honest choice over guessing which single cell should keep the value."""

    def __init__(self):
        super().__init__()
        self.grid: list[list[str]] = []
        self._pending: dict[int, tuple[int, str]] = {}  # col -> (rows remaining, text)
        self._row = -1
        self._col = 0
        self._in_cell = False
        self._buf: list[str] = []
        self._rowspan = self._colspan = 1

    def _fill_pending(self) -> None:
        while self._col in self._pending:
            rows_left, text = self._pending[self._col]
            self.grid[self._row].append(text)
            if rows_left <= 1:
                del self._pending[self._col]
            else:
                self._pending[self._col] = (rows_left - 1, text)
            self._col += 1

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row += 1
            self.grid.append([])
            self._col = 0
        elif tag == "td":
            self._fill_pending()
            self._in_cell = True
            self._buf = []
            a = dict(attrs)
            self._rowspan = int(a.get("rowspan") or 1)
            self._colspan = int(a.get("colspan") or 1)

    def handle_data(self, data):
        if self._in_cell:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "td":
            text = "".join(self._buf).strip()
            for i in range(self._colspan):
                self.grid[self._row].append(text)
                if self._rowspan > 1:
                    self._pending[self._col + i] = (self._rowspan - 1, text)
            self._col += self._colspan
            self._in_cell = False
        elif tag == "tr":
            self._fill_pending()  # a rowspan may extend past the row's last explicit <td>


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def html_table_to_markdown(table_html: str) -> str:
    """One HTML <table> (our own adapters' output only: table/tr/td, optional rowspan/colspan)
    as a Markdown table. Always pair with `TABLE_STRUCTURE_WARNING` -- this re-represents the
    same structure, it does not verify or fix it."""
    parser = _TableGridParser()
    parser.feed(table_html)
    grid = parser.grid
    if not grid:
        return ""
    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    lines = [
        "| " + " | ".join(_cell(c) for c in grid[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in grid[1:]:
        lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
    return "\n".join(lines)


def overlapping_fragments(
    target_bbox: list[float], candidates: list[Block], min_overlap_ratio: float = 0.3,
) -> list[str]:
    """Text of every block in `candidates` at least `min_overlap_ratio` of whose *own* box lies
    inside `target_bbox` -- i.e. the fragment sits (mostly) inside the visual block, even if it
    pokes out a little. Deduplicated, reading order (top-to-bottom, left-to-right). Geometry only,
    no claim that a fragment semantically belongs to the block.

    The ratio is measured against the fragment's own area, NOT min(fragment, target): a visual block
    that happens to sit entirely inside one big text block (e.g. a native PDF that reports a whole
    table as a single text blob around a figure) would otherwise pull that blob's full text in --
    the figure is fully covered, so a smaller-box ratio is always 1.0. Dividing by the fragment's
    own area rejects such an enclosing block (only a tiny fraction of it is inside the figure) while
    still keeping genuine small labels that lie within the block. See design.md "Rohtext-Liste:
    Bbox-Overlap-Heuristik" and the risk noted there."""
    tx0, ty0, tx1, ty1 = target_bbox
    seen: set[str] = set()
    hits: list[tuple[float, float, str]] = []
    for b in candidates:
        text = (b.text or "").strip()
        if not text:
            continue
        x0, y0, x1, y1 = b.bbox
        if _own_overlap_ratio(target_bbox, b.bbox) < min_overlap_ratio:
            continue
        if text not in seen:
            seen.add(text)
            hits.append((y0, x0, text))
    hits.sort()
    return [t for _, _, t in hits]


def _own_overlap_ratio(target_bbox: list[float], own_bbox: list[float]) -> float:
    """Fraction of `own_bbox`'s area that lies inside `target_bbox` (0.0 if they do not overlap)."""
    tx0, ty0, tx1, ty1 = target_bbox
    x0, y0, x1, y1 = own_bbox
    inter = max(0.0, min(tx1, x1) - max(tx0, x0)) * max(0.0, min(ty1, y1) - max(ty0, y0))
    own_area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return inter / own_area if own_area > 0 else 0.0


def assign_fragments(
    target_bboxes: list[list[float]], candidates: list[Block], min_overlap_ratio: float = 0.3,
) -> list[list[str]]:
    """Exclusive version of `overlapping_fragments` over several visual blocks at once: each candidate
    text is assigned to AT MOST ONE target -- the one whose box it sits in most (highest own-area
    overlap ratio, provided that ratio clears `min_overlap_ratio`). Returns one fragment list per
    target, aligned to `target_bboxes`, each deduplicated and in reading order. This prevents the
    same found text from showing up under two overlapping components. On a tie the earliest target
    in the list wins (stable). Geometry only, no claim of semantic membership."""
    buckets: list[list[tuple[float, float, str]]] = [[] for _ in target_bboxes]
    seen: list[set[str]] = [set() for _ in target_bboxes]
    for b in candidates:
        text = (b.text or "").strip()
        if not text:
            continue
        best_idx, best_ratio = -1, min_overlap_ratio
        for i, target in enumerate(target_bboxes):
            ratio = _own_overlap_ratio(target, b.bbox)
            if ratio > best_ratio:  # strictly greater: first target keeps a tie
                best_idx, best_ratio = i, ratio
        if best_idx < 0:
            continue
        x0, y0, x1, y1 = b.bbox
        if text not in seen[best_idx]:
            seen[best_idx].add(text)
            buckets[best_idx].append((y0, x0, text))
    return [[t for _, _, t in sorted(bucket)] for bucket in buckets]
