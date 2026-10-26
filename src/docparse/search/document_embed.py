"""Document-level embeddings: one `document_summary` embedding (from title+summary, see
`docparse.digest.summary`) and one `document_fulltext` embedding (from the full Markdown digest,
hard-capped). Both share `page=0` as the sentinel for "not tied to one page" (see
`format.EmbeddingItem`).

The cap on `document_fulltext` is load-bearing, not a tidiness choice: EmbeddingGemma 2 does not
limit input length itself (`model.max_seq_length` is effectively unbounded), and feeding it a
long enough document causes a real CUDA out-of-memory on an 8 GB card -- not a graceful slowdown.
Measured on the largest digest in the dataset (`gd1-001147`, 39,398 chars): 19,839 tokens still
ran, 21,339 tokens OOM'd while building the attention mask (tried to allocate 5.78 GiB). The
20,000-character limit below sits well under that cliff across the char/token ratios observed.
A document above the limit gets a `document_fulltext` embedding of its *beginning* only, not the
whole document -- `document_summary` (always computed from the unclipped title+summary) remains
the primary whole-document representation.

`embed_document_cloud_summary` is a third, independent function: it embeds the parallel
cloud-model summary (`docparse.digest.cloud_summary`, see
`openspec/changes/cloud-document-summary/`) as its own `document_summary_cloud` kind, additive
to -- and never replacing -- the `document_summary` embedding above (same page=0 sentinel, but a
distinct `kind` so the two can be told apart and compared later in `retrieval-eval`).
"""
import numpy as np

from ..digest.cloud_summary import CloudDocumentSummary
from ..digest.summary import DocumentSummary
from ..models.lifecycle import ModelManager
from .format import EmbeddingItem

DOCUMENT_PAGE_SENTINEL = 0
FULLTEXT_CHAR_LIMIT = 20_000


def _encode_text(manager: ModelManager, text: str) -> np.ndarray:
    model = manager.load("embedding")
    return np.asarray(model.encode(text, prompt_name="Document"))


def embed_document(
    manager: ModelManager, summary: DocumentSummary, full_markdown: str,
) -> tuple[list[EmbeddingItem], np.ndarray]:
    keys: list[str] = []
    kinds: list[str] = []
    vectors: list[np.ndarray] = []

    summary_text = f"{summary.title}\n\n{summary.summary}".strip()
    if summary_text and summary.status == "ok":
        keys.append("DOCUMENT/SUMMARY")
        kinds.append("document_summary")
        vectors.append(_encode_text(manager, summary_text))

    if full_markdown.strip():
        keys.append("DOCUMENT/FULLTEXT")
        kinds.append("document_fulltext")
        vectors.append(_encode_text(manager, full_markdown[:FULLTEXT_CHAR_LIMIT]))

    if not vectors:
        return [], np.zeros((0, 0), dtype=np.float32)
    matrix = np.stack(vectors).astype(np.float32)
    items = [
        EmbeddingItem(f"{summary.doc_id}/{k}", summary.doc_id, DOCUMENT_PAGE_SENTINEL, kind, row)
        for row, (k, kind) in enumerate(zip(keys, kinds))
    ]
    return items, matrix


def embed_document_cloud_summary(
    manager: ModelManager, cloud_summary: CloudDocumentSummary,
) -> tuple[list[EmbeddingItem], np.ndarray]:
    """Embeds the cloud-model title+summary as a `document_summary_cloud` item. No embedding is
    produced for a missing/`error` cloud summary -- the caller (the search runner) simply has
    nothing to add for that document this run, rather than erroring."""
    summary_text = f"{cloud_summary.title}\n\n{cloud_summary.summary}".strip()
    if not summary_text or cloud_summary.status != "ok":
        return [], np.zeros((0, 0), dtype=np.float32)
    vector = _encode_text(manager, summary_text)
    matrix = vector.reshape(1, -1).astype(np.float32)
    item = EmbeddingItem(
        f"{cloud_summary.doc_id}/DOCUMENT/SUMMARY_CLOUD", cloud_summary.doc_id,
        DOCUMENT_PAGE_SENTINEL, "document_summary_cloud", 0,
    )
    return [item], matrix
