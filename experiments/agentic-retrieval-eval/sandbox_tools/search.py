"""Minimal, dependency-light search CLI for inside the sandbox container (task 2.2).

Deliberately does NOT import `docparse` -- the sandbox image has no PaddlePaddle/PP-OCR stack,
only `sentence-transformers` (CPU), `numpy`, and stdlib `sqlite3`. Re-implements just the two
read paths the agent needs, against the exact same on-disk formats the production pipeline
writes (see `src/docparse/search/format.py` for `EmbeddingIndex`/`EmbeddingItem`,
`src/docparse/enrich/format.py` for `PageEnrichment`/`VisualBlock`, and
`src/docparse/search/fulltext.py` for the FTS5 schema/query quoting this mirrors).

Usage inside the container:
    python sandbox_tools/search.py vector "PSRR" --top-k 5
    python sandbox_tools/search.py fulltext "PSRR" --top-k 5

Expects the sandbox layout mounted at SANDBOX_ROOT (default /sandbox):
    enrich/<doc>/<page>.json       (PageEnrichment, identical in both variants)
    search/embeddings.npy          (float32 matrix, L2-normalized rows)
    search/embeddings.json         ({"version", "dim", "items": [...]})
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np

SANDBOX_ROOT = Path(os.environ.get("SANDBOX_ROOT", "/sandbox"))


# --- vector search --------------------------------------------------------------

def _load_index(root: Path) -> tuple[list[dict], np.ndarray]:
    meta = json.loads((root / "search" / "embeddings.json").read_text())
    vectors = np.load(root / "search" / "embeddings.npy")
    return meta["items"], vectors


def _encode_query(text: str) -> np.ndarray:
    # Imported lazily: a `fulltext`-only invocation should not pay the model-load cost.
    from sentence_transformers import SentenceTransformer

    model_id = os.environ.get("EMBEDDING_MODEL_ID", "google/embeddinggemma-2")
    model = SentenceTransformer(model_id, device="cpu")
    return np.asarray(model.encode(text, prompt_name="SearchQuery"))


def vector_search(query: str, top_k: int, root: Path = SANDBOX_ROOT) -> list[dict]:
    items, vectors = _load_index(root)
    if vectors.shape[0] == 0 or not query.strip():
        return []
    query_vec = _encode_query(query)
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vec) + 1e-12
    sims = (vectors @ query_vec) / norms
    order = np.argsort(-sims)[:top_k]
    by_row = {i["row"]: i for i in items}
    return [
        {**{k: v for k, v in by_row[int(i)].items() if k != "row"}, "score": float(sims[i])}
        for i in order
    ]


# --- fulltext search (FTS5, falls back to substring scan like fulltext.py) -----

def _enriched_documents(root: Path) -> list[tuple[str, str, int, str, str]]:
    """(key, doc_id, page, kind, text) tuples -- same shape as docparse's `Document`,
    re-derived from the raw PageEnrichment JSON instead of importing docparse."""
    docs = []
    for path in sorted((root / "enrich").glob("*/*.json")):
        e = json.loads(path.read_text(encoding="utf-8"))
        doc_id, page = e["doc_id"], e["page"]
        narrative = e.get("narrative_text", "")
        if narrative.strip():
            docs.append((f"{doc_id}/{page:04d}/NARRATIVE", doc_id, page, "narrative", narrative))
        for vb in e.get("visual_blocks", []):
            if vb.get("status") != "ok":
                continue
            label = f"{vb['type']}_{vb['position']}"
            if vb.get("description"):
                docs.append((f"{doc_id}/{page:04d}/{label}/DESC", doc_id, page, "visual_desc", vb["description"]))
            if vb.get("content_text"):
                docs.append((f"{doc_id}/{page:04d}/{label}/CONTENT", doc_id, page, "visual_content", vb["content_text"]))
    return docs


def _fts5_available() -> bool:
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()


def _fts5_query(query: str) -> str:
    terms = query.split()
    return " ".join(f'"{t}"' for t in terms) if terms else '""'


def fulltext_search(query: str, top_k: int, root: Path = SANDBOX_ROOT) -> list[dict]:
    if not query.strip():
        return []
    docs = _enriched_documents(root)
    if _fts5_available():
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE docs USING fts5(key, doc_id, page UNINDEXED, kind, text)")
        con.executemany("INSERT INTO docs VALUES (?, ?, ?, ?, ?)", docs)
        try:
            rows = con.execute(
                "SELECT key, doc_id, page, kind, text FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?",
                (_fts5_query(query), top_k),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [{"key": r[0], "doc_id": r[1], "page": r[2], "kind": r[3], "text": r[4]} for r in rows]
    terms = query.lower().split()
    hits = [d for d in docs if all(t in d[4].lower() for t in terms)]
    return [{"key": d[0], "doc_id": d[1], "page": d[2], "kind": d[3], "text": d[4]} for d in hits[:top_k]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="search.py")
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("vector", "fulltext"):
        p = sub.add_parser(name)
        p.add_argument("query")
        p.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args(argv)
    hits = vector_search(args.query, args.top_k) if args.mode == "vector" else fulltext_search(args.query, args.top_k)
    print(json.dumps(hits, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
