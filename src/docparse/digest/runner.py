"""Batch run: write one Markdown digest per document. Deterministic and cheap (no model calls),
so there is no skip/force distinction -- every call simply (re)writes."""
from dataclasses import dataclass, field
from pathlib import Path

from ..parse.format import RESULTS_DIR
from . import document as D


@dataclass
class Counts:
    done: int = 0
    errors: int = 0
    messages: list[str] = field(default_factory=list)


def run(doc_ids: list[str], root: Path = RESULTS_DIR, log=print) -> Counts:
    counts = Counts()
    for doc_id in doc_ids:
        try:
            path = D.write_digest(doc_id, root)
        except Exception as e:  # one bad document must not stop the run
            counts.errors += 1
            counts.messages.append(f"{doc_id}: {type(e).__name__}: {e}")
            continue
        counts.done += 1
        log(f"digest   {doc_id:<35} -> {path}")
    return counts
