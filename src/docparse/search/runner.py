"""Batch run: embed every enriched page not already in the index (incremental -- see
design.md "Reproduzierbare, inkrementelle Ablage"). `--force` rebuilds the whole index.
`run_documents` is a separate, second pass: one `document_summary` + `document_fulltext`
embedding per document that has a Markdown digest (`docparse.digest`), appended to the same
index -- see `document_embed.py`."""
from pathlib import Path

from ..digest.document import DIGEST_SUBDIR
from ..digest.summary import generate_summary, read_summary, summary_path, write_summary
from ..enrich.format import ENRICH_SUBDIR
from ..enrich.format import read_result as read_enrichment
from ..models.lifecycle import ModelManager
from ..parse.format import RESULTS_DIR
from ..parse.render import PAGES_DIR, page_image_path
from . import document_embed as DE
from . import embed as E
from .format import EmbeddingIndex


def enriched_pages(root: Path = RESULTS_DIR) -> list[Path]:
    return sorted((root / ENRICH_SUBDIR).glob("*/*.json"))


def digests(root: Path = RESULTS_DIR) -> list[Path]:
    return sorted((root / DIGEST_SUBDIR).glob("*.md"))


def run(
    manager: ModelManager, force: bool = False, results_dir: Path = RESULTS_DIR,
    pages_dir: Path = PAGES_DIR, expected_dim: int | None = None, log=print,
) -> tuple[EmbeddingIndex, int, int]:
    """Returns (index, pages embedded this run, pages already done and skipped)."""
    index = EmbeddingIndex() if force else EmbeddingIndex.load(results_dir, expected_dim)
    done_pages = set() if force else index.doc_pages()
    embedded = skipped = 0
    for path in enriched_pages(results_dir):
        enrichment = read_enrichment(path)
        if (enrichment.doc_id, enrichment.page) in done_pages:
            skipped += 1
            continue
        png = page_image_path(enrichment.doc_id, enrichment.page, pages_dir)
        items, vectors = E.embed_page(manager, enrichment, png)
        if items:
            index = index.add(items, vectors)
        index.save(results_dir)
        embedded += 1
        log(f"search   {enrichment.doc_id} p{enrichment.page:<4d} {len(items):3d} embeddings")
    return index, embedded, skipped


def run_documents(
    manager: ModelManager, index: EmbeddingIndex, force: bool = False,
    results_dir: Path = RESULTS_DIR, log=print,
) -> tuple[EmbeddingIndex, int, int]:
    """Returns (index, documents embedded this run, documents already done and skipped)."""
    done_docs = set() if force else {
        doc_id for doc_id, page in index.doc_pages() if page == DE.DOCUMENT_PAGE_SENTINEL
    }
    embedded = skipped = 0
    for path in digests(results_dir):
        doc_id = path.stem
        if doc_id in done_docs:
            skipped += 1
            continue
        full_markdown = path.read_text(encoding="utf-8")
        sp = summary_path(doc_id, results_dir)
        if sp.exists() and not force:
            summary = read_summary(sp)
        else:
            summary = generate_summary(manager, doc_id, full_markdown)
            write_summary(summary, results_dir)
        items, vectors = DE.embed_document(manager, summary, full_markdown)
        if items:
            index = index.add(items, vectors)
        index.save(results_dir)
        embedded += 1
        log(f"search   {doc_id:<35} document-level: {len(items)} embeddings")
    return index, embedded, skipped
