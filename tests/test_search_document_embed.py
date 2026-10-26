import numpy as np

from docparse.digest.cloud_summary import CloudDocumentSummary
from docparse.digest.summary import DocumentSummary
from docparse.search.document_embed import (
    DOCUMENT_PAGE_SENTINEL,
    FULLTEXT_CHAR_LIMIT,
    embed_document,
    embed_document_cloud_summary,
)


class FakeEmbeddingModel:
    def __init__(self):
        self.seen_texts = []

    def encode(self, text, prompt_name=None):
        self.seen_texts.append(text)
        return np.zeros(4, dtype=np.float32)


class FakeManager:
    def __init__(self):
        self.model = FakeEmbeddingModel()

    def load(self, key):
        assert key == "embedding"
        return self.model


def test_embed_document_produces_summary_and_fulltext_kinds():
    manager = FakeManager()
    summary = DocumentSummary("doc-1", "Title", "Summary text")
    items, vectors = embed_document(manager, summary, "# doc-1\n\nfull markdown content")
    kinds = {i.kind for i in items}
    assert kinds == {"document_summary", "document_fulltext"}
    assert vectors.shape == (2, 4)
    assert all(i.doc_id == "doc-1" and i.page == DOCUMENT_PAGE_SENTINEL for i in items)
    assert [i.row for i in items] == [0, 1]


def test_summary_text_combines_title_and_summary():
    manager = FakeManager()
    summary = DocumentSummary("doc-1", "My Title", "My summary.")
    embed_document(manager, summary, "content")
    assert "My Title" in manager.model.seen_texts[0] and "My summary." in manager.model.seen_texts[0]


def test_fulltext_is_truncated_to_the_char_limit():
    manager = FakeManager()
    summary = DocumentSummary("doc-1", "T", "S")
    long_text = "x" * (FULLTEXT_CHAR_LIMIT + 5000)
    embed_document(manager, summary, long_text)
    fulltext_input = manager.model.seen_texts[1]
    assert len(fulltext_input) == FULLTEXT_CHAR_LIMIT


def test_empty_summary_and_fulltext_produce_nothing():
    manager = FakeManager()
    items, vectors = embed_document(manager, DocumentSummary("doc-1", "", ""), "   ")
    assert items == [] and vectors.shape == (0, 0)


def test_degenerate_summary_is_not_embedded_but_fulltext_still_is():
    manager = FakeManager()
    summary = DocumentSummary("doc-1", "doc-1", "", status="degenerate")
    items, vectors = embed_document(manager, summary, "# doc-1\n\nreal digest content")
    kinds = {i.kind for i in items}
    assert kinds == {"document_fulltext"}  # no document_summary row for degenerate output
    assert vectors.shape == (1, 4)


# --- embed_document_cloud_summary: parallel cloud-model summary embedding ------------------

def test_embed_document_cloud_summary_produces_distinct_kind():
    manager = FakeManager()
    cloud_summary = CloudDocumentSummary("doc-1", "Cloud Title", "Cloud summary text.", status="ok")
    items, vectors = embed_document_cloud_summary(manager, cloud_summary)
    assert len(items) == 1
    assert items[0].kind == "document_summary_cloud"
    assert items[0].doc_id == "doc-1" and items[0].page == DOCUMENT_PAGE_SENTINEL
    assert vectors.shape == (1, 4)
    assert "Cloud Title" in manager.model.seen_texts[0] and "Cloud summary text." in manager.model.seen_texts[0]


def test_embed_document_cloud_summary_is_distinguishable_from_local_document_summary():
    manager = FakeManager()
    local_items, _ = embed_document(manager, DocumentSummary("doc-1", "Local", "Local summary."), "content")
    cloud_items, _ = embed_document_cloud_summary(
        manager, CloudDocumentSummary("doc-1", "Cloud", "Cloud summary.", status="ok"),
    )
    assert {i.kind for i in local_items} & {i.kind for i in cloud_items} == set()


def test_embed_document_cloud_summary_empty_for_error_status():
    manager = FakeManager()
    cloud_summary = CloudDocumentSummary("doc-1", "doc-1", "", status="error", error="boom")
    items, vectors = embed_document_cloud_summary(manager, cloud_summary)
    assert items == [] and vectors.shape == (0, 0)
    assert manager.model.seen_texts == []  # no wasted embedding call for a failed cloud summary


def test_embed_document_cloud_summary_empty_for_missing_text():
    manager = FakeManager()
    cloud_summary = CloudDocumentSummary("doc-1", "", "", status="ok")
    items, vectors = embed_document_cloud_summary(manager, cloud_summary)
    assert items == [] and vectors.shape == (0, 0)
