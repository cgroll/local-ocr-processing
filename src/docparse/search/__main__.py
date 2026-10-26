"""CLI: uv run python -m docparse.search {run,query}"""
import argparse
import sys
from pathlib import Path

from ..models import Registry, RegistryError
from ..models.lifecycle import ModelManager
from ..parse.format import RESULTS_DIR
from ..parse.render import PAGES_DIR
from . import runner
from .format import EmbeddingIndex
from .fulltext import FullTextIndex
from .query import search


def cmd_run(args) -> int:
    registry = Registry.load(args.config)
    manager = ModelManager(registry)
    expected_dim = registry.get("embedding").params["dim"]
    try:
        index, embedded, skipped = runner.run(
            manager, force=args.force, results_dir=args.results_dir, pages_dir=args.pages_dir,
            expected_dim=expected_dim,
        )
        index, doc_embedded, doc_skipped = runner.run_documents(
            manager, index, force=args.force, results_dir=args.results_dir,
        )
    finally:
        manager.unload_all()
    by_kind: dict[str, int] = {}
    for i in index.items:
        by_kind[i.kind] = by_kind.get(i.kind, 0) + 1
    print(f"\nembedded {embedded} pages, skipped {skipped} (already done)")
    print(f"embedded {doc_embedded} documents, skipped {doc_skipped} (already done)")
    print(f"index: {len(index.items)} vectors, dim {index.dim}")
    for kind, n in sorted(by_kind.items()):
        print(f"  {kind:<16} {n}")
    return 0


def cmd_query(args) -> int:
    embedding_index = EmbeddingIndex.load(args.results_dir)
    fulltext_index = FullTextIndex.build(args.results_dir)
    manager = None
    if not args.fulltext_only and embedding_index.dim:
        manager = ModelManager(Registry.load(args.config))
    try:
        hits = search(args.text, embedding_index, fulltext_index, manager, top_k=args.top_k)
    finally:
        if manager is not None:
            manager.unload_all()
    if not hits:
        print("no hits")
        return 0
    for h in hits:
        score = f"{h.score:.3f}" if h.score is not None else "-"
        print(f"{h.source:<9} {score:>6} {h.doc_id:<20} p{h.page:<4} {h.kind:<15} {h.key}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docparse.search")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="embed every enriched page not already in the index (resumable)")
    p.add_argument("--force", action="store_true", help="rebuild the whole index")
    p.add_argument("--pages-dir", type=Path, default=PAGES_DIR)
    p.add_argument("--config", type=Path, default=Path("models.toml"))
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("query", help="manual lookup: fulltext + vector hits for one text query")
    p.add_argument("text")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--fulltext-only", action="store_true", help="skip the embedding model (faster, no GPU)")
    p.add_argument("--config", type=Path, default=Path("models.toml"))
    p.set_defaults(func=cmd_query)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RegistryError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
