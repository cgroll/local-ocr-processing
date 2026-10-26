"""CLI: uv run python -m docparse.enrich run"""
import argparse
import sys
from pathlib import Path

from ..dataset import manifest
from ..models import Registry, RegistryError
from ..models.lifecycle import ModelManager
from ..parse.format import RESULTS_DIR
from ..parse.render import PAGES_DIR
from ..parse.select import RAW_DIR, select_pages
from . import runner


def cmd_run(args) -> int:
    docs, skipped = select_pages(manifest.load(args.manifest), args.raw_dir, set(args.docs) or None, args.limit)
    for s in skipped:
        print(f"SKIP {s}")
    print(f"{len(docs)} documents, {sum(len(d.pages) for d in docs)} pages")
    registry = Registry.load(args.config)
    manager = ModelManager(registry)
    try:
        counts = runner.run(docs, manager, force=args.force, results_dir=args.results_dir, pages_dir=args.pages_dir)
    finally:
        manager.unload_all()
    print(f"\ndone {counts.done}  skipped {counts.skipped}  page errors {counts.errors}  block errors {counts.block_errors}")
    for m in counts.messages:
        print(f"ERROR {m}")
    return 1 if counts.errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docparse.enrich")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="enrich manifest pages: text source, narrative text, crops + descriptions (resumable)")
    p.add_argument("--docs", nargs="*", default=[], help="restrict to these document ids")
    p.add_argument("--limit", type=int, help="process at most this many pages in total")
    p.add_argument("--force", action="store_true", help="recompute pages that already have an ok result")
    p.add_argument("--manifest", type=Path, default=manifest.DEFAULT_PATH)
    p.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    p.add_argument("--pages-dir", type=Path, default=PAGES_DIR)
    p.add_argument("--config", type=Path, default=Path("models.toml"))
    p.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RegistryError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
