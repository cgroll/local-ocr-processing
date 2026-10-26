"""Full-text index over the same text corpus as the embeddings: narrative text, table content,
and visual-block descriptions. Uses SQLite FTS5 (checked once, see `fts5_available`), falling
back to a plain substring scan if a particular Python/sqlite3 build lacks it -- see design.md
"Volltextindex: SQLite FTS5"."""
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..enrich.format import ENRICH_SUBDIR
from ..enrich.format import read_result as read_enrichment
from ..parse.format import RESULTS_DIR


def fts5_available() -> bool:
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()


@dataclass
class Document:
    key: str  # same key convention as EmbeddingItem, e.g. "d/0001/NARRATIVE", "d/0001/table_0/CONTENT"
    doc_id: str
    page: int
    kind: str  # "narrative" | "visual_desc" | "visual_content"
    text: str


def enriched_documents(root: Path = RESULTS_DIR) -> list[Document]:
    """One `Document` per narrative text and per visual block's description/content, read
    straight from the enrichment results on disk (no separate storage for the full-text
    corpus -- it's the same text the embeddings are built from)."""
    docs = []
    for path in sorted((root / ENRICH_SUBDIR).glob("*/*.json")):
        e = read_enrichment(path)
        if e.narrative_text.strip():
            docs.append(Document(f"{e.doc_id}/{e.page:04d}/NARRATIVE", e.doc_id, e.page, "narrative", e.narrative_text))
        for vb in e.visual_blocks:
            if vb.status != "ok":
                continue
            label = f"{vb.type}_{vb.position}"
            if vb.description:
                docs.append(Document(f"{e.doc_id}/{e.page:04d}/{label}/DESC", e.doc_id, e.page, "visual_desc", vb.description))
            if vb.content_text:
                docs.append(Document(f"{e.doc_id}/{e.page:04d}/{label}/CONTENT", e.doc_id, e.page, "visual_content", vb.content_text))
    return docs


def _fts5_query(query: str) -> str:
    """Quote each term so punctuation/special FTS5 query syntax in the raw input can't break
    parsing (a search box should never 500 on a stray quote or colon)."""
    terms = query.split()
    return " ".join(f'"{t}"' for t in terms) if terms else '""'


class FullTextIndex:
    """Backed by SQLite FTS5 when available, else an in-memory substring scan over the same
    `Document` list -- callers get the same `search()` interface either way."""

    def __init__(self, documents: list[Document], use_fts5: bool | None = None):
        self._documents = documents
        self._use_fts5 = fts5_available() if use_fts5 is None else use_fts5
        self._con = None
        if self._use_fts5:
            self._con = sqlite3.connect(":memory:")
            self._con.execute("CREATE VIRTUAL TABLE docs USING fts5(key, doc_id, page UNINDEXED, kind, text)")
            self._con.executemany(
                "INSERT INTO docs (key, doc_id, page, kind, text) VALUES (?, ?, ?, ?, ?)",
                [(d.key, d.doc_id, d.page, d.kind, d.text) for d in documents],
            )

    @classmethod
    def build(cls, root: Path = RESULTS_DIR) -> "FullTextIndex":
        return cls(enriched_documents(root))

    def search(self, query: str, limit: int = 20) -> list[Document]:
        if not query.strip():
            return []
        if self._use_fts5:
            try:
                rows = self._con.execute(
                    "SELECT key, doc_id, page, kind, text FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?",
                    (_fts5_query(query), limit),
                ).fetchall()
            except sqlite3.OperationalError:
                return []  # a query FTS5 cannot parse at all -> no hits, not a crash
            return [Document(*r) for r in rows]
        terms = query.lower().split()
        hits = [d for d in self._documents if all(t in d.text.lower() for t in terms)]
        return hits[:limit]
