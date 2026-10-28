"""Assembles one page's Markdown section in page order: narrative text with real headings (from
the chosen text source's block types) and each visual block -- with its description, the caption
found next to it, Markdown table (for tables) and overlapping raw-text fragments -- placed where it
sits on the page."""
from dataclasses import dataclass, field
from pathlib import Path

from ..enrich import blocks as B
from ..enrich.format import PageEnrichment
from ..parse.format import RESULTS_DIR, PageResult
from . import markdown as M

VISUAL_HEADINGS = {"table": "Tabelle", "chart": "Diagramm", "figure": "Abbildung"}


# A layout `caption` belongs to the visual block it sits next to: vertical gap at most this fraction
# of the page height, and it must overlap the visual horizontally.
CAPTION_MAX_GAP_RATIO = 0.06


@dataclass(frozen=True)
class Section:
    """One rendered piece of a page's Markdown, with the page boxes it was built from (pixels, see
    `parse.format`). A visual section lists its own box plus the boxes of its caption and of the
    fragments placed under it; a narrative section lists its block's box. `bboxes` is empty only
    for text that has no source box (the no-text-source fallback)."""
    text: str
    bboxes: list[list[float]] = field(default_factory=list)


def _h_overlap(a: list[float], b: list[float]) -> float:
    return min(a[2], b[2]) - max(a[0], b[0])


def _v_gap(a: list[float], b: list[float]) -> float:
    return max(0.0, max(a[1], b[1]) - min(a[3], b[3]))


def _assign_captions(visuals: list, layout, narrative: list, page_height: float) -> dict[int, tuple[str, set[int]]]:
    """visual index -> (caption text, ids of the narrative blocks it was read from). The layout
    engine says *where* a caption is, the text source says *what* it reads: the text blocks lying
    in a layout `caption` box become that visual's caption (nearest visual with horizontal overlap
    and a small gap; each caption goes to at most one visual, each visual takes at most one)."""
    if layout is None or not visuals:
        return {}
    pairs = []  # (gap, caption index, visual index)
    captions = [b for b in layout.blocks if b.type == "caption"]
    for ci, cap in enumerate(captions):
        for vi, vb in enumerate(visuals):
            if _h_overlap(cap.bbox, vb.bbox) <= 0:
                continue
            gap = _v_gap(cap.bbox, vb.bbox)
            if gap <= CAPTION_MAX_GAP_RATIO * page_height:
                pairs.append((gap, ci, vi))
    out: dict[int, tuple[str, set[int]]] = {}
    used: set[int] = set()
    for _, ci, vi in sorted(pairs):
        if ci in used or vi in out:
            continue
        inside = [b for b in narrative if (b.text or "").strip()
                  and M._own_overlap_ratio(captions[ci].bbox, b.bbox) >= 0.5]
        if not inside:
            continue
        inside.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
        out[vi] = (" ".join(b.text.strip() for b in inside), {id(b) for b in inside})
        used.add(ci)
    return out


def _in_page_order(narrative: list, visuals: list) -> list[tuple[str, object]]:
    """Narrative blocks (already in reading order) with each visual block placed by position, see
    `B.insert_by_position`."""
    merged = B.insert_by_position(
        [("n", b, b.bbox) for b in narrative], [("v", vi, vb.bbox) for vi, vb in enumerate(visuals)],
    )
    return [(kind, payload) for kind, payload, _ in merged]


def render_page_sections(enrichment: PageEnrichment, source: PageResult | None, root: Path = RESULTS_DIR) -> list[Section]:
    """The page's Markdown below the `## Seite N` heading, as sections in page order, each with its
    source boxes. Empty sections are dropped. `render_page` is exactly these sections joined."""
    pymupdf_result = B.read_ok("pymupdf", enrichment.doc_id, enrichment.page, root)
    ocr_result = B.read_ok("ocr", enrichment.doc_id, enrichment.page, root)
    layout_result = B.read_ok("layout", enrichment.doc_id, enrichment.page, root)

    narrative: list = []
    if source is not None:
        narrative = B.narrative_blocks(source, [vb.bbox for vb in enrichment.visual_blocks], layout_result)
    box_of = {id(b): b.bbox for b in narrative}  # before captions are removed from `narrative`

    # Exclude pymupdf `cell` blocks from the fragment pool: they are the table's own text and would
    # just duplicate it under the table's "found texts" (the table already shows its content).
    candidates = [b for b in ((pymupdf_result.blocks if pymupdf_result else [])
                              + (ocr_result.blocks if ocr_result else [])) if b.type != "cell"]

    # Assign each found text to at most one visual block (the one it sits in most), so the same
    # fragment never appears under two overlapping components.
    visuals = [vb for vb in enrichment.visual_blocks if vb.status == "ok"]
    fragments_per_block = M.assign_fragment_boxes([vb.bbox for vb in visuals], candidates)

    captions = _assign_captions(visuals, layout_result, narrative, source.height if source else 0)
    consumed = set().union(*(ids for _, ids in captions.values())) if captions else set()
    narrative = [b for b in narrative if id(b) not in consumed]

    def render_visual(vi: int) -> Section:
        vb, fragments = visuals[vi], fragments_per_block[vi]
        out = [f"### {VISUAL_HEADINGS.get(vb.type, vb.type)}: {vb.label}"]
        boxes = [list(vb.bbox)]
        if vb.description:
            out.append(vb.description)
        if vi in captions:
            out.append(f"*{captions[vi][0]}*")
            boxes += [list(box_of[i]) for i in captions[vi][1]]
        if vb.type == "table" and vb.content_text and "<table" in vb.content_text:
            table_md = M.html_table_to_markdown(vb.content_text)
            if table_md:
                out.append(table_md)
                out.append(M.TABLE_STRUCTURE_WARNING)
                fragments = []  # the table already carries its text; fragments would only repeat it
        if fragments:
            out.append(M.RAW_FRAGMENTS_LABEL)
            out.append(", ".join(text for text, _ in fragments))
            boxes += [box for _, box in fragments]
        return Section("\n\n".join(out), boxes)

    sections: list[Section] = []
    if source is not None:
        for kind, payload in _in_page_order(narrative, visuals):
            if kind == "n":
                section = Section(M.render_narrative_block(payload), [list(payload.bbox)])
            else:
                section = render_visual(payload)
            if section.text:
                sections.append(section)
    else:
        if enrichment.narrative_text:
            sections.append(Section(enrichment.narrative_text))
        sections.extend(render_visual(vi) for vi in range(len(visuals)))
    return sections


def render_page(enrichment: PageEnrichment, source: PageResult | None, root: Path = RESULTS_DIR) -> str:
    parts = [f"## Seite {enrichment.page}"] + [s.text for s in render_page_sections(enrichment, source, root)]
    return "\n\n".join(p for p in parts if p)
