"""CLI: uv run python -m docparse.parse {run,validate,summary}"""
import argparse
import sys
from pathlib import Path

from ..dataset import manifest
from ..models import Registry, RegistryError
from . import runner
from .format import RESULTS_DIR, validate_tree
from .render import DEFAULT_DPI
from .select import RAW_DIR, select_pages
from .summary import summarize


def cmd_run(args) -> int:
    engines = args.engines.split(",")
    unknown = [e for e in engines if e not in runner.ENGINES]
    if unknown:
        print(f"ERROR unknown engine '{unknown[0]}', valid: {', '.join(runner.ENGINES)}", file=sys.stderr)
        return 2
    docs, skipped = select_pages(manifest.load(args.manifest), args.raw_dir, set(args.docs) or None, args.limit)
    for s in skipped:
        print(f"SKIP {s}")
    print(f"{len(docs)} documents, {sum(len(d.pages) for d in docs)} pages, engines: {', '.join(engines)}")
    registry = Registry.load(args.config)
    results = runner.run_all(engines, docs, registry, dpi=args.dpi, force=args.force, results_dir=args.results_dir)
    print("\nengine     done skipped errors")
    for key, c in results.items():
        print(f"{key:<9} {c.done:>5} {c.skipped:>7} {c.errors:>6}")
    for c in results.values():
        for m in c.messages:
            print(f"ERROR {m}")
    return 1 if any(c.errors for c in results.values()) else 0


def cmd_validate(args) -> int:
    count, errors = validate_tree(args.results_dir, args.engines.split(",") if args.engines else None)
    for e in errors:
        print(f"ERROR {e}")
    print(f"{count} files checked, {len(errors)} errors")
    return 1 if errors else 0


def cmd_summary(args) -> int:
    print(summarize(args.results_dir, args.engines.split(",") if args.engines else None))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docparse.parse")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="parse manifest pages with the chosen engines (resumable)")
    p.add_argument("--engines", default=",".join(runner.ENGINES))
    p.add_argument("--docs", nargs="*", default=[], help="restrict to these document ids")
    p.add_argument("--limit", type=int, help="process at most this many pages in total")
    p.add_argument("--force", action="store_true", help="recompute pages that already have an ok result")
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    p.add_argument("--manifest", type=Path, default=manifest.DEFAULT_PATH)
    p.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    p.add_argument("--config", type=Path, default=Path("models.toml"))
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("validate", help="check all result files")
    p.add_argument("--engines")
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("summary", help="pages, errors, timings and block counts per engine")
    p.add_argument("--engines")
    p.set_defaults(func=cmd_summary)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RegistryError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
