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


def narrative_text(source: PageResult) -> str:
    """Non-visual blocks of the chosen text source, in column-aware reading order, joined as one
    text blob."""
    candidates = [b for b in source.blocks if b.type not in NON_NARRATIVE_TYPES]
    blocks = reading_order(candidates, source.width, source.height)
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
