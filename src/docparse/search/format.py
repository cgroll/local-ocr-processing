"""Storage for the multimodal embedding index: one flat array of vectors plus a metadata JSON
list describing what each row is (which page/block/kind it belongs to). No vector-DB server --
see design.md ("Vektor-Ablage: flaches Array + Metadaten-JSON") -- the dataset is small enough
(low thousands of rows at most) for brute-force cosine similarity in memory."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ..parse.format import RESULTS_DIR

VERSION = 1
SEARCH_SUBDIR = "search"
# "page_text"/"page_image": one per page. "visual_image"/"visual_desc"/"visual_content": one per
# enriched visual block (content only for tables with a content_text). "document_summary"/
# "document_fulltext": one per document (page=0 sentinel, see document_embed.py), not per page.
# "document_summary_cloud": the same page=0 sentinel, but from a cloud flagship model's summary
# (docparse.digest.cloud_summary) instead of the local `describe` model -- additive, parallel
# comparison data, see openspec/changes/cloud-document-summary/proposal.md.
EMBEDDING_KINDS = (
    "page_text", "page_image", "visual_image", "visual_desc", "visual_content",
    "document_summary", "document_fulltext", "document_summary_cloud",
)


class DimensionMismatch(ValueError):
    pass


@dataclass
class EmbeddingItem:
    key: str  # unique id, e.g. "ds-lm317/0004/PAGE_TEXT" or "ds-lm317/0004/table_1/DESC"
    doc_id: str
    page: int
    kind: str  # one of EMBEDDING_KINDS
    row: int  # index into the vectors array this item's embedding lives at


def search_dir(root: Path = RESULTS_DIR) -> Path:
    return root / SEARCH_SUBDIR


def vectors_path(root: Path = RESULTS_DIR) -> Path:
    return search_dir(root) / "embeddings.npy"


def metadata_path(root: Path = RESULTS_DIR) -> Path:
    return search_dir(root) / "embeddings.json"


@dataclass
class EmbeddingIndex:
    items: list[EmbeddingItem] = field(default_factory=list)
    vectors: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))

    @property
    def dim(self) -> int:
        return int(self.vectors.shape[1]) if self.vectors.ndim == 2 else 0

    def doc_pages(self) -> set[tuple[str, int]]:
        return {(i.doc_id, i.page) for i in self.items}

    def doc_ids_with_kind(self, kind: str) -> set[str]:
        """Document ids that already have an embedding of the given `kind` -- used for the
        resumable per-kind skip logic of document-level passes like `run_documents_cloud`,
        where several kinds (document_summary, document_fulltext, document_summary_cloud) share
        the same page=0 sentinel and so can't be told apart by `doc_pages()` alone."""
        return {i.doc_id for i in self.items if i.kind == kind}

    def add(self, new_items: list[EmbeddingItem], new_vectors: np.ndarray) -> "EmbeddingIndex":
        """Returns a new index with `new_items`/`new_vectors` appended (rows renumbered)."""
        if self.vectors.size and new_vectors.size and self.vectors.shape[1] != new_vectors.shape[1]:
            raise DimensionMismatch(f"existing dim {self.vectors.shape[1]} != new dim {new_vectors.shape[1]}")
        offset = self.vectors.shape[0]
        renumbered = [EmbeddingItem(i.key, i.doc_id, i.page, i.kind, i.row + offset) for i in new_items]
        vectors = new_vectors if not self.vectors.size else np.concatenate([self.vectors, new_vectors], axis=0)
        return EmbeddingIndex([*self.items, *renumbered], vectors)

    def save(self, root: Path = RESULTS_DIR) -> None:
        d = search_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        np.save(vectors_path(root), self.vectors.astype(np.float32))
        metadata_path(root).write_text(json.dumps(
            {"version": VERSION, "dim": self.dim, "items": [asdict(i) for i in self.items]}, indent=1,
        ))

    @classmethod
    def load(cls, root: Path = RESULTS_DIR, expected_dim: int | None = None) -> "EmbeddingIndex":
        """Empty index if nothing was saved yet. Raises DimensionMismatch if the stored vectors'
        width disagrees with the stored `dim` or with `expected_dim` (e.g. the live model's)."""
        if not metadata_path(root).exists():
            return cls()
        meta = json.loads(metadata_path(root).read_text())
        vectors = np.load(vectors_path(root))
        dim = meta["dim"]
        if vectors.shape[0] and vectors.shape[1] != dim:
            raise DimensionMismatch(f"stored dim {dim} does not match vectors shape {vectors.shape}")
        if expected_dim is not None and dim and dim != expected_dim:
            raise DimensionMismatch(f"stored dim {dim} does not match expected dim {expected_dim}")
        items = [EmbeddingItem(**i) for i in meta["items"]]
        return cls(items, vectors)
