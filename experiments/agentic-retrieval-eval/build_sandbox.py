"""Sandbox builder (tasks 3.1/3.2): builds two throwaway, self-contained copies of the corpus
the agent is allowed to search -- `sandbox_local/` (local `describe`-model summaries) and
`sandbox_cloud/` (Gemini-4-Argon summaries from `cloud-document-summary`). Run on the HOST with
the project venv (needs `docparse` for `EmbeddingIndex`), not inside the sandbox container.

Identical in both variants (see design.md "Context"): `enrich/`, `digest/<doc>.md`, `pages/`.
Different: the one summary file per document, and a filtered copy of the embedding index (one
`kind` masked out per variant -- `document_summary_cloud` for "local", `document_summary` for
"cloud"). Ground truth (`experiments/vlm-qa-test/questions.py`/`judgments.py`) is never a source
here -- this script only ever reads from `data/results/{enrich,digest,search}` and `data/pages`.

Usage:
    uv run python experiments/agentic-retrieval-eval/build_sandbox.py --out-dir /tmp/sandboxes
"""
import argparse
import shutil
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from docparse.search.format import EmbeddingIndex, EmbeddingItem  # noqa: E402

RESULTS_DIR = REPO_ROOT / "data" / "results"
PAGES_DIR = REPO_ROOT / "data" / "pages"

VARIANTS = {
    "local": {"summary_glob": "*.summary.json", "exclude_kind": "document_summary_cloud"},
    "cloud": {"summary_glob": "*.cloud_summary.json", "exclude_kind": "document_summary"},
}


def filtered_index(index: EmbeddingIndex, exclude_kind: str) -> EmbeddingIndex:
    """New index with every item of `exclude_kind` removed, vectors/rows renumbered to match."""
    keep = [i for i in index.items if i.kind != exclude_kind]
    if not keep:
        return EmbeddingIndex([], np.zeros((0, index.dim), dtype=np.float32))
    vectors = index.vectors[[i.row for i in keep]].astype(np.float32)
    renumbered = [EmbeddingItem(i.key, i.doc_id, i.page, i.kind, row) for row, i in enumerate(keep)]
    return EmbeddingIndex(renumbered, vectors)


def build_variant(variant: str, dest: Path, results_dir: Path = RESULTS_DIR, pages_dir: Path = PAGES_DIR) -> None:
    spec = VARIANTS[variant]
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    # Shared: enrich/, digest/<doc>.md, pages/ -- identical across both variants.
    shutil.copytree(results_dir / "enrich", dest / "enrich")
    (dest / "digest").mkdir()
    for md in (results_dir / "digest").glob("*.md"):
        shutil.copy2(md, dest / "digest" / md.name)
    shutil.copytree(pages_dir, dest / "pages")

    # Variant-specific: only this variant's summary files.
    for summary_file in (results_dir / "digest").glob(spec["summary_glob"]):
        shutil.copy2(summary_file, dest / "digest" / summary_file.name)

    # Variant-specific: embedding index with the other variant's document-level kind removed.
    index = EmbeddingIndex.load(results_dir)
    filtered = filtered_index(index, spec["exclude_kind"])
    filtered.save(dest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True, help="parent dir for sandbox_local/ and sandbox_cloud/")
    parser.add_argument("--variant", choices=list(VARIANTS), help="build only this variant (default: both)")
    args = parser.parse_args(argv)

    variants = [args.variant] if args.variant else list(VARIANTS)
    for variant in variants:
        dest = args.out_dir / f"sandbox_{variant}"
        build_variant(variant, dest)
        print(f"{variant}: built {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
