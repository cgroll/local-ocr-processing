"""CLI: uv run python -m docparse.digest {run,cloud-summary}"""
import argparse
import sys
from pathlib import Path

from ..enrich.format import ENRICH_SUBDIR
from ..parse.format import RESULTS_DIR
from . import cloud_summary as CS
from . import runner
from .document import DIGEST_SUBDIR


def _available_doc_ids(root: Path) -> list[str]:
    d = root / ENRICH_SUBDIR
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


def _digested_doc_ids(root: Path) -> list[str]:
    d = root / DIGEST_SUBDIR
    return sorted(p.stem for p in d.glob("*.md")) if d.exists() else []


def cmd_run(args) -> int:
    doc_ids = args.docs or _available_doc_ids(args.results_dir)
    print(f"{len(doc_ids)} documents")
    counts = runner.run(doc_ids, args.results_dir)
    print(f"\ndone {counts.done}  errors {counts.errors}")
    for m in counts.messages:
        print(f"ERROR {m}")
    return 1 if counts.errors else 0


def cmd_cloud_summary_run(args) -> int:
    """Second, parallel summary source (Gemini 4 Argon via Vertex AI), see
    openspec/changes/cloud-document-summary/. Needs an existing Markdown digest per document
    (`docparse.digest run`) -- does not touch the local `describe`-model summary."""
    doc_ids = args.docs or _digested_doc_ids(args.results_dir)
    print(f"{len(doc_ids)} documents")
    client = CS.build_client()
    counts = CS.run(client, doc_ids, args.results_dir, force=args.force)
    print(f"\ndone {counts.done}  skipped {counts.skipped}  errors {counts.errors}")
    print(
        f"tokens {counts.total_input_tokens}in/{counts.total_output_tokens}out tok  "
        f"cost ${counts.total_cost_usd:.4f}"
    )
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
    p = sub.add_parser(
        "cloud-summary",
        help="generate a parallel document title+summary via a cloud flagship model (Gemini 4 Argon)",
    )
    p.add_argument("--docs", nargs="*", default=[], help="restrict to these document ids")
    p.add_argument("--force", action="store_true", help="recompute documents that already have an ok cloud summary")
    p.set_defaults(func=cmd_cloud_summary_run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
