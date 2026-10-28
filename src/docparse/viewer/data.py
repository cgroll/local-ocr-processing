"""Collect what the viewer shows: per-page results of all engines and per-document coverage."""
import json
from dataclasses import dataclass
from pathlib import Path

import markdown

from ..dataset.manifest import Entry
from ..digest.page import render_page
from ..enrich.blocks import choose_text_source
from ..enrich.format import read_result as read_enrichment
from ..enrich.format import result_path as enrich_result_path
from ..parse.format import RESULTS_DIR, read_result, result_path
from .sanitize import sanitize_markdown_html, sanitize_table

ENGINES = ("pymupdf", "layout", "ocr", "vl")
# Same wording `digest/page.py:render_page` uses for the heading, so the "no content beyond the
# heading" check below matches exactly rather than guessing a prefix.
NO_ENRICHMENT_NOTE = "*Keine Anreicherung für diese Seite vorhanden.*"
NO_TEXT_SOURCE_NOTE = "*Keine Textquelle für diese Seite ermittelt.*"


def page_numbers(entry: Entry) -> list[int]:
    """1-based pages in scope for a manifest entry."""
    if entry.page_range:
        first, last = (int(x) for x in entry.page_range.split("-"))
        return list(range(first, last + 1))
    return list(range(1, int(entry.pages or 0) + 1))


def embed_json(obj) -> str:
    """JSON safe inside a <script> block: no '<' left, so '</script>' and '<!--' cannot occur."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _load_engine(engine: str, doc_id: str, page: int, results_dir: Path) -> dict:
    path = result_path(engine, doc_id, page, results_dir)
    if not path.exists():
        return {"state": "missing"}
    try:
        result = read_result(path)
    except (OSError, ValueError, TypeError, KeyError) as e:
        return {"state": "error", "error": f"result file unreadable: {e}"}
    if result.status == "error":
        return {"state": "error", "error": result.error or "unknown error"}
    blocks = []
    for i, b in enumerate(result.blocks):
        d = {k: v for k, v in vars(b).items() if v is not None}
        if "html" in d:
            d["html"] = sanitize_table(d["html"])
        d["id"] = f"{engine}:{i}"
        blocks.append(d)
    return {
        "state": "ok", "seconds": result.seconds, "version": result.engine_version,
        "size": [result.width, result.height], "blocks": blocks,
    }


def _page_markdown(doc_id: str, page: int, root: Path) -> str:
    """Same text as `document-digest` would render for this page -- see `digest/page.py:
    render_page`. Deliberately not `write_digest`/`render_document`: those join a whole
    document's pages, which would be wasted work for rendering a single page here."""
    heading = f"## Seite {page}"
    enrich_path = enrich_result_path(doc_id, page, root)
    if not enrich_path.exists():
        return f"{heading}\n\n{NO_ENRICHMENT_NOTE}"
    enrichment = read_enrichment(enrich_path)
    _, source = choose_text_source(doc_id, page, root)
    text = render_page(enrichment, source, root)
    if text.strip() == heading:
        text = f"{text}\n\n{NO_TEXT_SOURCE_NOTE}"
    return text


def markdown_html(doc_id: str, page: int, root: Path = RESULTS_DIR) -> str:
    """Flowing Markdown representation of one page, rendered to sanitized HTML for the viewer's
    Markdown tab -- same fixed text-source choice as production (`choose_text_source`), no
    per-engine selection like the Original/Rekonstruktion columns."""
    text = _page_markdown(doc_id, page, root)
    html = markdown.markdown(text, extensions=["tables"])
    return sanitize_markdown_html(html)


def _visual_blocks_payload(doc_id: str, page: int, root: Path) -> list[dict]:
    """Enrichment visual blocks for the viewer's Markdown-tab gallery -- figures, charts AND tables.
    Each carries its description, the raw text fragments whose boxes overlap the block (same
    geometry heuristic and pymupdf+ocr candidate pool the digest uses, see digest/page.py), and,
    for tables, the recognised table HTML (sanitised like any other table HTML in the viewer).
    A second, separate read of the enrichment file rather than reworking the markdown path, see
    design.md Decision 3. Empty list if the page has no enrichment at all."""
    from ..digest.markdown import assign_fragments
    from ..enrich.blocks import read_ok

    enrich_path = enrich_result_path(doc_id, page, root)
    if not enrich_path.exists():
        return []
    enrichment = read_enrichment(enrich_path)

    pymupdf_result = read_ok("pymupdf", doc_id, page, root)
    ocr_result = read_ok("ocr", doc_id, page, root)
    # Exclude pymupdf `cell` blocks (the table's own per-cell text) from the fragment pool, so a
    # table's "found texts" is not just its own content duplicated. See digest/page.py.
    candidates = [b for b in ((pymupdf_result.blocks if pymupdf_result else [])
                              + (ocr_result.blocks if ocr_result else [])) if b.type != "cell"]

    # Each found text is assigned to at most one block (the one it sits in most), same as the digest,
    # so the viewer gallery never shows the same fragment under two overlapping components. Only
    # `ok` blocks take part (a failed block, which the gallery hides, must not steal fragments from a
    # valid neighbour); non-ok blocks get an empty list.
    ok_idx = [i for i, vb in enumerate(enrichment.visual_blocks) if vb.status == "ok"]
    ok_fragments = assign_fragments([enrichment.visual_blocks[i].bbox for i in ok_idx], candidates)
    fragments_by_i = dict(zip(ok_idx, ok_fragments))

    payload = []
    for i, vb in enumerate(enrichment.visual_blocks):
        item = {
            "type": vb.type, "label": vb.label, "bbox": vb.bbox,
            "description": vb.description, "status": vb.status,
            "fragments": fragments_by_i.get(i, []),
        }
        if vb.type == "table" and vb.content_text and "<table" in vb.content_text:
            item["html"] = sanitize_table(vb.content_text)
        payload.append(item)
    return payload


def page_data(entry: Entry, page: int, results_dir: Path = RESULTS_DIR) -> dict:
    """All engine results of one page; failed and absent results are marked, tables are sanitized."""
    engines = {e: _load_engine(e, entry.id, page, results_dir) for e in ENGINES}
    size = next((r["size"] for r in engines.values() if r["state"] == "ok"), None)
    return {
        "doc": entry.id, "title": entry.title or entry.id, "page": page,
        "size": size, "engines": engines,
        "markdown_html": markdown_html(entry.id, page, results_dir),
        "visual_blocks": _visual_blocks_payload(entry.id, page, results_dir),
    }


@dataclass
class DocCoverage:
    entry: Entry
    pages: list[int]  # pages in scope
    counts: dict[str, dict[str, int]]  # engine -> {ok, error, missing}
    with_results: list[int]  # pages that have a result from at least one engine


def coverage(entry: Entry, results_dir: Path = RESULTS_DIR) -> DocCoverage:
    pages = page_numbers(entry)
    counts = {e: {"ok": 0, "error": 0, "missing": 0} for e in ENGINES}
    with_results = []
    for p in pages:
        found = False
        for e in ENGINES:
            path = result_path(e, entry.id, p, results_dir)
            if not path.exists():
                counts[e]["missing"] += 1
                continue
            found = True
            try:
                ok = read_result(path).status == "ok"
            except (OSError, ValueError, TypeError, KeyError):
                ok = False
            counts[e]["ok" if ok else "error"] += 1
        if found:
            with_results.append(p)
    return DocCoverage(entry, pages, counts, with_results)


def index_data(entries: list[Entry], results_dir: Path = RESULTS_DIR) -> list[DocCoverage]:
    """Coverage of every document that has at least one result, in manifest order."""
    return [c for c in (coverage(e, results_dir) for e in entries) if c.with_results]
