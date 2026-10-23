"""CLI: uv run python -m docparse.viewer build [--docs ID ...]"""
import argparse
import sys
from pathlib import Path

from ..dataset import manifest
from ..parse.format import RESULTS_DIR
from .build import OUT_DIR, build


def cmd_build(args) -> int:
    report = build(args.out_dir, args.manifest, args.results_dir, set(args.docs) or None)
    for m in report.missing_images:
        print(f"MISSING image {m}")
    print(f"{report.docs} documents, {report.pages} pages")
    print(f"open {report.index.resolve()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docparse.viewer")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build", help="generate the static viewer from the parse results")
    p.add_argument("--docs", nargs="*", default=[], help="restrict to these document ids")
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--manifest", type=Path, default=manifest.DEFAULT_PATH)
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    p.set_defaults(func=cmd_build)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
