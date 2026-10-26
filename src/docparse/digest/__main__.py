"""CLI: uv run python -m docparse.digest run"""
import argparse
import sys
from pathlib import Path

from ..enrich.format import ENRICH_SUBDIR
from ..parse.format import RESULTS_DIR
from . import runner


def _available_doc_ids(root: Path) -> list[str]:
    d = root / ENRICH_SUBDIR
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


def cmd_run(args) -> int:
    doc_ids = args.docs or _available_doc_ids(args.results_dir)
    print(f"{len(doc_ids)} documents")
    counts = runner.run(doc_ids, args.results_dir)
    print(f"\ndone {counts.done}  errors {counts.errors}")
    for m in counts.messages:
        print(f"ERROR {m}")
    return 1 if counts.errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docparse.digest")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="write one Markdown digest per document from its enriched pages")
    p.add_argument("--docs", nargs="*", default=[], help="restrict to these document ids")
    p.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
