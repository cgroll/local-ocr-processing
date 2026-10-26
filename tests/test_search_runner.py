from pathlib import Path

import numpy as np
from PIL import Image

from docparse.digest.cloud_summary import CloudDocumentSummary, cloud_summary_path, write_cloud_summary
from docparse.digest.summary import summary_path, write_summary, DocumentSummary
from docparse.enrich.format import PageEnrichment, write_result as write_enrichment
from docparse.search import runner as R
from docparse.search.format import DimensionMismatch


class FakeEmbeddingModel:
    def encode(self, x, prompt_name=None):
        return np.zeros(4, dtype=np.float32)


class FakeDescribeHandle:
    def __init__(self):
        self.calls = 0

    def generate_text(self, prompt, max_new_tokens=None):
        self.calls += 1
        return "TITLE: Fake Title\nSUMMARY: Fake summary."


class FakeManager:
    """Dispatches by key, like the real ModelManager -- "embedding" for vectors, "describe" for
    the title/summary generation that `run_documents` also needs."""
    def __init__(self):
        self.embedding = FakeEmbeddingModel()
        self.describe = FakeDescribeHandle()

    def load(self, key):
        return self.describe if key == "describe" else self.embedding


def _setup_page(root: Path, doc_id: str, page: int, text: str = "hello"):
    write_enrichment(PageEnrichment(doc_id, page, "pymupdf", narrative_text=text), root)
    png_dir = root.parent / "pages" / doc_id
    png_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (10, 10), "white").save(png_dir / f"{page:04d}.png")


def test_run_embeds_all_enriched_pages_once(tmp_path):
    results_dir = tmp_path / "results"
    _setup_page(results_dir, "d1", 1)
    _setup_page(results_dir, "d1", 2)
    pages_dir = tmp_path / "pages"

    index, embedded, skipped = R.run(FakeManager(), results_dir=results_dir, pages_dir=pages_dir, log=lambda *a: None)
    assert embedded == 2 and skipped == 0
    assert index.doc_pages() == {("d1", 1), ("d1", 2)}


def test_run_is_incremental_then_skips_done_pages(tmp_path):
    results_dir = tmp_path / "results"
    _setup_page(results_dir, "d1", 1)
    pages_dir = tmp_path / "pages"
    R.run(FakeManager(), results_dir=results_dir, pages_dir=pages_dir, log=lambda *a: None)

    _setup_page(results_dir, "d2", 1)  # a second document arrives later
    index, embedded, skipped = R.run(FakeManager(), results_dir=results_dir, pages_dir=pages_dir, log=lambda *a: None)
    assert embedded == 1 and skipped == 1  # only d2 is new; d1 was already done
    assert index.doc_pages() == {("d1", 1), ("d2", 1)}


def test_force_rebuilds_from_scratch(tmp_path):
    results_dir = tmp_path / "results"
    _setup_page(results_dir, "d1", 1)
    pages_dir = tmp_path / "pages"
    R.run(FakeManager(), results_dir=results_dir, pages_dir=pages_dir, log=lambda *a: None)

    index, embedded, skipped = R.run(FakeManager(), force=True, results_dir=results_dir, pages_dir=pages_dir, log=lambda *a: None)
    assert embedded == 1 and skipped == 0


def test_run_rejects_mismatched_expected_dim(tmp_path):
    results_dir = tmp_path / "results"
    _setup_page(results_dir, "d1", 1)
    pages_dir = tmp_path / "pages"
    R.run(FakeManager(), results_dir=results_dir, pages_dir=pages_dir, log=lambda *a: None)  # dim 4

    try:
        R.run(FakeManager(), results_dir=results_dir, pages_dir=pages_dir, expected_dim=768, log=lambda *a: None)
        assert False, "expected DimensionMismatch"
    except DimensionMismatch:
        pass


def _setup_digest(root: Path, doc_id: str, text: str = "# doc\n\nsome content"):
    d = root / "digest"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{doc_id}.md").write_text(text)


def test_run_documents_embeds_each_digest_and_generates_a_summary(tmp_path):
    results_dir = tmp_path / "results"
    _setup_digest(results_dir, "d1")
    manager = FakeManager()

    index, embedded, skipped = R.run_documents(manager, R.EmbeddingIndex(), results_dir=results_dir, log=lambda *a: None)
    assert embedded == 1 and skipped == 0
    assert manager.describe.calls == 1
    assert index.doc_pages() == {("d1", 0)}
    assert summary_path("d1", results_dir).exists()


def test_run_documents_skips_already_embedded_documents(tmp_path):
    results_dir = tmp_path / "results"
    _setup_digest(results_dir, "d1")
    manager = FakeManager()
    index, _, _ = R.run_documents(manager, R.EmbeddingIndex(), results_dir=results_dir, log=lambda *a: None)

    _setup_digest(results_dir, "d2")
    index, embedded, skipped = R.run_documents(manager, index, results_dir=results_dir, log=lambda *a: None)
    assert embedded == 1 and skipped == 1
    assert index.doc_pages() == {("d1", 0), ("d2", 0)}


def test_run_documents_reuses_existing_summary_without_regenerating(tmp_path):
    results_dir = tmp_path / "results"
    _setup_digest(results_dir, "d1")
    write_summary(DocumentSummary("d1", "Pre-existing Title", "Pre-existing summary."), results_dir)
    manager = FakeManager()

    R.run_documents(manager, R.EmbeddingIndex(), results_dir=results_dir, log=lambda *a: None)
    assert manager.describe.calls == 0  # summary already on disk, describe is never called


def test_run_documents_force_regenerates_summary_and_embeddings(tmp_path):
    results_dir = tmp_path / "results"
    _setup_digest(results_dir, "d1")
    manager = FakeManager()
    index, _, _ = R.run_documents(manager, R.EmbeddingIndex(), results_dir=results_dir, log=lambda *a: None)

    index, embedded, skipped = R.run_documents(manager, index, force=True, results_dir=results_dir, log=lambda *a: None)
    assert embedded == 1 and skipped == 0
    assert manager.describe.calls == 2


# --- run_documents_cloud: third, independent pass for the parallel cloud summary --------------

def test_run_documents_cloud_embeds_documents_with_an_ok_cloud_summary(tmp_path):
    results_dir = tmp_path / "results"
    _setup_digest(results_dir, "d1")
    write_cloud_summary(CloudDocumentSummary("d1", "Cloud Title", "Cloud summary.", status="ok"), results_dir)
    manager = FakeManager()

    index, embedded, skipped = R.run_documents_cloud(manager, R.EmbeddingIndex(), results_dir=results_dir, log=lambda *a: None)
    assert embedded == 1 and skipped == 0
    assert any(i.kind == "document_summary_cloud" and i.doc_id == "d1" for i in index.items)


def test_run_documents_cloud_coexists_with_local_document_summary(tmp_path):
    results_dir = tmp_path / "results"
    _setup_digest(results_dir, "d1")
    write_cloud_summary(CloudDocumentSummary("d1", "Cloud Title", "Cloud summary.", status="ok"), results_dir)
    manager = FakeManager()

    index, _, _ = R.run_documents(manager, R.EmbeddingIndex(), results_dir=results_dir, log=lambda *a: None)
    index, _, _ = R.run_documents_cloud(manager, index, results_dir=results_dir, log=lambda *a: None)
    kinds = {i.kind for i in index.items if i.doc_id == "d1"}
    assert {"document_summary", "document_fulltext", "document_summary_cloud"} <= kinds


def test_run_documents_cloud_skips_already_embedded_documents(tmp_path):
    results_dir = tmp_path / "results"
    _setup_digest(results_dir, "d1")
    write_cloud_summary(CloudDocumentSummary("d1", "Cloud Title", "Cloud summary.", status="ok"), results_dir)
    manager = FakeManager()
    index, _, _ = R.run_documents_cloud(manager, R.EmbeddingIndex(), results_dir=results_dir, log=lambda *a: None)

    _setup_digest(results_dir, "d2")
    write_cloud_summary(CloudDocumentSummary("d2", "Cloud Title 2", "Cloud summary 2.", status="ok"), results_dir)
    index, embedded, skipped = R.run_documents_cloud(manager, index, results_dir=results_dir, log=lambda *a: None)
    assert embedded == 1 and skipped == 1  # only d2 is new; d1 was already done


def test_run_documents_cloud_without_new_summaries_leaves_index_unchanged(tmp_path):
    results_dir = tmp_path / "results"
    _setup_digest(results_dir, "d1")
    write_cloud_summary(CloudDocumentSummary("d1", "Cloud Title", "Cloud summary.", status="ok"), results_dir)
    manager = FakeManager()
    index, _, _ = R.run_documents_cloud(manager, R.EmbeddingIndex(), results_dir=results_dir, log=lambda *a: None)
    before = len(index.items)

    index, embedded, skipped = R.run_documents_cloud(manager, index, results_dir=results_dir, log=lambda *a: None)
    assert embedded == 0 and skipped == 1
    assert len(index.items) == before


def test_run_documents_cloud_ignores_documents_without_a_cloud_summary(tmp_path):
    results_dir = tmp_path / "results"
    _setup_digest(results_dir, "d1")  # no cloud summary written for d1
    manager = FakeManager()

    index, embedded, skipped = R.run_documents_cloud(manager, R.EmbeddingIndex(), results_dir=results_dir, log=lambda *a: None)
    assert embedded == 0 and skipped == 0
    assert index.items == []
