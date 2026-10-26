"""Assembles one document's Markdown digest from all its enriched pages -- see page.py for a
single page's section. Deterministic, no model calls: a rerun with unchanged inputs produces the
same output."""
from pathlib import Path

from ..enrich import blocks as B
from ..enrich.format import ENRICH_SUBDIR
from ..enrich.format import read_result as read_enrichment
from ..parse.format import RESULTS_DIR
from . import page as P

DIGEST_SUBDIR = "digest"


def digest_path(doc_id: str, root: Path = RESULTS_DIR) -> Path:
    return root / DIGEST_SUBDIR / f"{doc_id}.md"


def enriched_pages_for_doc(doc_id: str, root: Path = RESULTS_DIR) -> list[Path]:
    return sorted((root / ENRICH_SUBDIR / doc_id).glob("*.json"))


def render_document(doc_id: str, root: Path = RESULTS_DIR) -> str:
    parts = [f"# {doc_id}"]
    for path in enriched_pages_for_doc(doc_id, root):
        enrichment = read_enrichment(path)
        if enrichment.status != "ok":
            continue
        _, source = B.choose_text_source(enrichment.doc_id, enrichment.page, root)
        parts.append(P.render_page(enrichment, source, root))
    return "\n\n".join(parts)


def write_digest(doc_id: str, root: Path = RESULTS_DIR) -> Path:
    path = digest_path(doc_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render_document(doc_id, root)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path
