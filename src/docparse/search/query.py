"""Combined query interface: full-text and vector hits for one text query, side by side, each
tagged with the signal it came from. No fusion/reranking formula -- see design.md ("Open
Questions": combining the two signals into one ranking is `retrieval-eval`'s job, not this one's)."""
from dataclasses import dataclass

import numpy as np

from ..models.lifecycle import ModelManager
from .format import EmbeddingIndex
from .fulltext import FullTextIndex


@dataclass
class SearchHit:
    source: str  # "fulltext" | "vector"
    key: str
    doc_id: str
    page: int
    kind: str
    score: float | None = None  # cosine similarity for vector hits, None for fulltext hits


def _cosine_top_k(query_vec: np.ndarray, vectors: np.ndarray, k: int) -> list[tuple[int, float]]:
    if vectors.shape[0] == 0:
        return []
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vec) + 1e-12
    sims = (vectors @ query_vec) / norms
    order = np.argsort(-sims)[:k]
    return [(int(i), float(sims[i])) for i in order]


def search(
    query: str, embedding_index: EmbeddingIndex, fulltext_index: FullTextIndex,
    manager: ModelManager | None = None, top_k: int = 10,
) -> list[SearchHit]:
    """Never raises for "no hits" -- returns an empty list. `manager` may be omitted to get
    fulltext-only results (e.g. when the embedding model isn't loaded)."""
    hits = [
        SearchHit("fulltext", d.key, d.doc_id, d.page, d.kind)
        for d in fulltext_index.search(query, top_k)
    ]
    if manager is not None and embedding_index.dim and query.strip():
        model = manager.load("embedding")
        query_vec = np.asarray(model.encode(query, prompt_name="SearchQuery"))
        by_row = {i.row: i for i in embedding_index.items}
        for row, score in _cosine_top_k(query_vec, embedding_index.vectors, top_k):
            item = by_row[row]
            hits.append(SearchHit("vector", item.key, item.doc_id, item.page, item.kind, score))
    return hits
