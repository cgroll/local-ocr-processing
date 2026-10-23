"""Manifest summary: per-group counts, native/scanned split, tag coverage and warnings."""
from collections import Counter

from .manifest import GROUPS, KINDS, Entry

GROUP_TARGETS = {"datasheet": 20, "report": 20, "scan": 10, "corpus-sample": 20}
CONTENT_TAGS = ("table", "schematic", "diagram", "formula", "plain-text")
MIN_DOCS_PER_TAG = 5


def summarize(entries: list[Entry]) -> tuple[str, list[str]]:
    """Return (report text, warnings)."""
    warnings = []
    lines = [f"{len(entries)} documents, {sum(e.page_count for e in entries)} pages", ""]

    lines.append(f"{'group':<15}{'docs':>5}{'target':>8}{'pages':>7}")
    for g in GROUPS:
        docs = [e for e in entries if e.group == g]
        target = GROUP_TARGETS[g]
        lines.append(f"{g:<15}{len(docs):>5}{target:>8}{sum(e.page_count for e in docs):>7}")
        if len(docs) < target / 2:
            warnings.append(f"group '{g}' has {len(docs)} documents, less than half of the target {target}")

    kinds = Counter(e.kind or "unverified" for e in entries)
    lines += ["", "kind: " + ", ".join(f"{k}={kinds.get(k, 0)}" for k in (*KINDS, "unverified"))]

    tag_counts = Counter(t for e in entries for t in e.tag_list)
    lines += ["", "tags:"]
    for tag in CONTENT_TAGS:
        n = tag_counts.get(tag, 0)
        gap = "  <- gap" if n < MIN_DOCS_PER_TAG else ""
        lines.append(f"  {tag:<12}{n:>3}{gap}")
        if gap:
            warnings.append(f"tag '{tag}' is carried by {n} documents, fewer than {MIN_DOCS_PER_TAG}")
    return "\n".join(lines), warnings
