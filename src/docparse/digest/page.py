"""Assembles one page's Markdown section: narrative text with real headings (from the chosen
text source's block types), then each visual block with its description, Markdown table (for
tables) and overlapping raw-text fragments."""
from pathlib import Path

from ..enrich import blocks as B
from ..enrich.format import PageEnrichment
from ..parse.format import RESULTS_DIR, PageResult
from . import markdown as M

VISUAL_HEADINGS = {"table": "Tabelle", "chart": "Diagramm", "figure": "Abbildung"}


def render_page(enrichment: PageEnrichment, source: PageResult | None, root: Path = RESULTS_DIR) -> str:
    parts = [f"## Seite {enrichment.page}"]

    if source is not None:
        candidates_narrative = [b for b in source.blocks if b.type not in B.VISUAL_TYPES]
        blocks = B.reading_order(candidates_narrative, source.width, source.height)
        for block in blocks:
            rendered = M.render_narrative_block(block)
            if rendered:
                parts.append(rendered)
    elif enrichment.narrative_text:
        parts.append(enrichment.narrative_text)

    pymupdf_result = B.read_ok("pymupdf", enrichment.doc_id, enrichment.page, root)
    ocr_result = B.read_ok("ocr", enrichment.doc_id, enrichment.page, root)
    candidates = (pymupdf_result.blocks if pymupdf_result else []) + (ocr_result.blocks if ocr_result else [])

    for vb in enrichment.visual_blocks:
        if vb.status != "ok":
            continue
        heading = VISUAL_HEADINGS.get(vb.type, vb.type)
        parts.append(f"### {heading}: {vb.label}")
        if vb.description:
            parts.append(vb.description)
        if vb.type == "table" and vb.content_text and "<table" in vb.content_text:
            table_md = M.html_table_to_markdown(vb.content_text)
            if table_md:
                parts.append(table_md)
                parts.append(M.TABLE_STRUCTURE_WARNING)
        fragments = M.overlapping_fragments(vb.bbox, candidates)
        if fragments:
            parts.append(M.RAW_FRAGMENTS_LABEL)
            parts.append(", ".join(fragments))

    return "\n\n".join(p for p in parts if p)
