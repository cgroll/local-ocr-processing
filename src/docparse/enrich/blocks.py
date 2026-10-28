"""Pure building blocks for page enrichment: text source choice, narrative text, visual-block
selection (figure/chart/table crops) and the decorative-icon filter. No model calls here -- see
`describe.py` for VLM descriptions."""
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from ..parse.format import PageResult, RESULTS_DIR, read_result
from ..parse.format import result_path as engine_result_path

VISUAL_TYPES = ("figure", "chart", "table")
# Types excluded from the narrative text blob and the text-source decision. `cell` is pymupdf's
# per-cell table text (see parse/adapters/pymupdf.py): it is for display/overlay only -- its content
# is already carried by the `table` block, so including it here would duplicate the whole table into
# the narrative text and the search corpus.
NON_NARRATIVE_TYPES = VISUAL_TYPES + ("cell",)
# Separates real figures/charts/tables from small decorative icons (e.g. the four TI
# "ordering/docs/support/design" marketing icons observed on ds-tps62130 p1, each
# 5000-7350 px^2) from genuine content (that page's table/chart/schematic are 30000+ px^2).
MIN_VISUAL_AREA_PX = 10_000


def _read_ok(engine: str, doc_id: str, page: int, root: Path) -> PageResult | None:
    path = engine_result_path(engine, doc_id, page, root)
    if not path.exists():
        return None
    result = read_result(path)
    return result if result.status == "ok" else None


def read_ok(engine: str, doc_id: str, page: int, root: Path = RESULTS_DIR) -> PageResult | None:
    """The engine's result for this page if it exists and succeeded, else None."""
    return _read_ok(engine, doc_id, page, root)


def choose_text_source(doc_id: str, page: int, root: Path = RESULTS_DIR) -> tuple[str, PageResult | None]:
    """`pymupdf` if it has any non-visual text, else `ocr` as a fallback for pure scans, else
    ("none", None) when neither engine produced a usable result."""
    pymupdf_result = _read_ok("pymupdf", doc_id, page, root)
    if pymupdf_result and any(b.text for b in pymupdf_result.blocks if b.type not in NON_NARRATIVE_TYPES):
        return "pymupdf", pymupdf_result
    ocr_result = _read_ok("ocr", doc_id, page, root)
    if ocr_result is not None:
        return "ocr", ocr_result
    return "none", None


# Column-aware reordering: PP-OCRv6 (and occasionally pymupdf on dense PDFs) orders blocks by
# raw y-position across the whole page, which interleaves left/right column text into word salad
# on multi-column pages (found via a real case: bs-f-831f-pdp-8-interface-manual-may65 p2 -- see
# AGENTS.md change history). The guard below only reorders when the page genuinely looks like
# clean newspaper-style columns; a datasheet with schematic labels scattered at many different
# x-positions, or a single-column page, falls back to the engine's own order unchanged.
COLUMN_GAP_RATIO = 0.08  # horizontal gap, as a fraction of page width, that starts a new column
MIN_COLUMNS, MAX_COLUMNS = 2, 3
MIN_BLOCKS_PER_COLUMN = 4
MIN_COLUMN_HEIGHT_RATIO = 0.3  # a column must span at least this fraction of the page height
MIN_MEDIAN_WORDS_PER_BLOCK = 3  # filters out scattered single-value labels, not running prose


def _x_clusters(blocks: list, page_width: float, gap_ratio: float = COLUMN_GAP_RATIO) -> list[list]:
    """Groups blocks by their left edge: a horizontal gap bigger than `gap_ratio * page_width`
    between consecutive distinct x0 values starts a new, further-right cluster."""
    xs = sorted({round(b.bbox[0]) for b in blocks})
    if not xs:
        return []
    gap = gap_ratio * page_width
    edges = [xs[0]]
    boundaries = [xs[0]]
    for x in xs[1:]:
        if x - edges[-1] > gap:
            boundaries.append(x)
        edges.append(x)
    groups = [[] for _ in boundaries]
    for b in blocks:
        x0 = round(b.bbox[0])
        idx = max(i for i, start in enumerate(boundaries) if start <= x0)
        groups[idx].append(b)
    return groups


def _looks_like_clean_columns(groups: list[list], page_height: float) -> bool:
    if not (MIN_COLUMNS <= len(groups) <= MAX_COLUMNS):
        return False
    for g in groups:
        if len(g) < MIN_BLOCKS_PER_COLUMN:
            return False
        yspan = max(b.bbox[3] for b in g) - min(b.bbox[1] for b in g)
        if yspan < MIN_COLUMN_HEIGHT_RATIO * page_height:
            return False
        word_counts = sorted(len((b.text or "").split()) for b in g)
        if word_counts[len(word_counts) // 2] < MIN_MEDIAN_WORDS_PER_BLOCK:
            return False
    return True


def reading_order(blocks: list, page_width: float, page_height: float) -> list:
    """Blocks in column-aware reading order when the page looks like genuine multi-column prose
    (left column top-to-bottom, then the next column top-to-bottom, ...); otherwise falls back
    to the engine's own `order` field unchanged."""
    by_order = sorted(blocks, key=lambda b: b.order if b.order is not None else 0)
    if page_width <= 0 or page_height <= 0:
        return by_order
    groups = _x_clusters(by_order, page_width)
    if not _looks_like_clean_columns(groups, page_height):
        return by_order
    groups.sort(key=lambda g: min(b.bbox[0] for b in g))  # left column first
    ordered = []
    for g in groups:
        ordered.extend(sorted(g, key=lambda b: b.bbox[1]))
    return ordered


def _inside(inner: list[float], outer: list[float]) -> float:
    """Fraction of `inner`'s area that lies inside `outer`."""
    inter = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0])) * max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    area = max(0.0, inner[2] - inner[0]) * max(0.0, inner[3] - inner[1])
    return inter / area if area > 0 else 0.0


def unclaimed_tables(source: PageResult, visual_bboxes: list[list[float]]) -> list:
    """`table` blocks of the text source that no visual block (layout figure/chart/table) covers.
    pymupdf's table finder also fires on ruled text (tables of contents, revision lists) that the
    layout model sees as plain text; such a table is not described as a visual block, so its text
    must stay in the narrative or it is lost for the digest and the search corpus."""
    return [b for b in source.blocks if b.type == "table" and (b.text or b.html)
            and not any(_inside(b.bbox, v) >= 0.5 for v in visual_bboxes)]


def insert_by_position(entries: list[tuple], extras: list[tuple]) -> list[tuple]:
    """`entries`/`extras` are (kind, payload, bbox) tuples; `entries` is in reading order. Each extra
    (taken top-to-bottom, left-to-right) goes right after the nearest entry above it -- the one with
    the greatest top edge at or above the extra's own, later list position winning ties. Entries
    count only if they share horizontal extent with it (so in multi-column text it stays in its own
    column), except earlier extras, which always count so a grid of figures keeps its order. With
    nothing above, it goes before the nearest sharing entry below, else to the end. The list order
    itself is not trusted for position: engines can list a footer first."""
    def h_overlap(a, b):
        return min(a[2], b[2]) - max(a[0], b[0])

    placed = {id(e) for e in extras}
    entries = list(entries)
    for extra in sorted(extras, key=lambda e: (e[2][1], e[2][0])):
        box = extra[2]
        sharing = [(j, e) for j, e in enumerate(entries)
                   if (id(e) in placed or h_overlap(e[2], box) > 0)]
        above = [(e[2][1], j) for j, e in sharing if e[2][1] <= box[1]]
        if above:
            at = max(above)[1] + 1
        else:
            below = [(e[2][1], j) for j, e in sharing]
            at = min(below, key=lambda t: (t[0], t[1]))[1] if below else len(entries)
        entries.insert(at, extra)
    return entries


def layout_order(blocks: list, layout: PageResult) -> list | None:
    """`blocks` (text-source blocks) in the layout model's reading order, or None if the layout has
    no ordered regions. Each block goes to the ordered layout region it lies in most (>= half of its
    own area); inside a region blocks follow top-to-bottom, left-to-right. Blocks no ordered region
    claims (headers, footers, stray text -- layout gives those no order) are placed by position
    among the rest."""
    regions = sorted((r for r in layout.blocks if r.order is not None), key=lambda r: r.order)
    if not regions:
        return None
    groups: list[list] = [[] for _ in regions]
    loose = []
    for b in blocks:
        best, best_ratio = -1, 0.5
        for i, r in enumerate(regions):
            ratio = _inside(b.bbox, r.bbox)
            if ratio >= best_ratio and (best < 0 or ratio > best_ratio):
                best, best_ratio = i, ratio
        (groups[best] if best >= 0 else loose).append(b)
    ordered = [b for g in groups for b in sorted(g, key=lambda b: (b.bbox[1], b.bbox[0]))]
    merged = insert_by_position([("n", b, b.bbox) for b in ordered], [("n", b, b.bbox) for b in loose])
    return [payload for _, payload, _ in merged]


def narrative_blocks(source: PageResult, visual_bboxes: list[list[float]], layout: PageResult | None = None) -> list:
    """Blocks of the chosen text source that make up the running text, in reading order: everything
    but visual blocks and `cell`s, plus pymupdf tables that no visual block covers. The order comes
    from the layout model when it has one for the page, else from the column heuristic."""
    candidates = [b for b in source.blocks if b.type not in NON_NARRATIVE_TYPES]
    candidates += unclaimed_tables(source, visual_bboxes)
    ordered = layout_order(candidates, layout) if layout is not None else None
    if ordered is None:
        plain = [b for b in candidates if b.type != "table"]
        ordered = reading_order(plain, source.width, source.height)
        merged = insert_by_position(
            [("n", b, b.bbox) for b in ordered], [("n", b, b.bbox) for b in candidates if b.type == "table"],
        )
        ordered = [payload for _, payload, _ in merged]
    return ordered


def narrative_text(
    source: PageResult, visual_bboxes: list[list[float]] | None = None, layout: PageResult | None = None,
) -> str:
    """Running text of the chosen text source (see `narrative_blocks`), joined as one text blob."""
    blocks = narrative_blocks(source, visual_bboxes or [], layout)
    parts = [b.markdown or b.text for b in blocks if (b.markdown or b.text)]
    return "\n\n".join(parts)


@dataclass
class VisualCandidate:
    type: str
    label: str
    bbox: list[float]
    position: int  # index among kept candidates on this page; layout gives no reading order


def visual_candidates(layout_result: PageResult, min_area_px: float = MIN_VISUAL_AREA_PX) -> list[VisualCandidate]:
    """`layout` blocks of type figure/chart/table over the minimum area, sorted top-to-bottom,
    left-to-right (the project's own `PP-DocLayoutV3` adapter does not set a reading order)."""
    blocks = sorted(
        (b for b in layout_result.blocks if b.type in VISUAL_TYPES),
        key=lambda b: (b.bbox[1], b.bbox[0]),
    )
    out = []
    for b in blocks:
        x0, y0, x1, y1 = b.bbox
        if (x1 - x0) * (y1 - y0) >= min_area_px:
            out.append(VisualCandidate(b.type, b.label, b.bbox, len(out)))
    return out


def crop_region(page_png: Path, bbox: list[float]) -> Image.Image:
    x0, y0, x1, y1 = (round(v) for v in bbox)
    with Image.open(page_png) as img:
        return img.convert("RGB").crop((x0, y0, x1, y1))


def table_content(
    table_rank: int, pymupdf_result: PageResult | None, vl_result: PageResult | None,
) -> tuple[str | None, str | None]:
    """Content text for the `table_rank`-th table candidate on the page (0-based, among table
    candidates only), preferring `vl`'s HTML when available -- it keeps row structure more
    reliably than `pymupdf`'s (see experiments/vlm-qa-test/README.md, "Follow-up A"). Matching is
    positional (`table_rank`-th table block in each engine's own block list): best-effort, since
    the engines don't share block identities, but table counts per page agree in practice."""
    for result, source_name in ((vl_result, "vl"), (pymupdf_result, "pymupdf")):
        if result is None:
            continue
        tables = [b for b in result.blocks if b.type == "table"]
        if table_rank < len(tables):
            content = tables[table_rank].html or tables[table_rank].markdown or tables[table_rank].text
            if content:
                return content, source_name
    return None, None
