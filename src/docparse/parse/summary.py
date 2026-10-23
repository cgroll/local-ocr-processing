"""Per-engine overview of the results on disk (no GPU needed)."""
import statistics
from collections import Counter
from pathlib import Path

from .format import RESULTS_DIR, read_result


def summarize(root: Path = RESULTS_DIR, engines: list[str] | None = None) -> str:
    rows = []
    for engine_dir in sorted(p for p in root.glob("*") if p.is_dir()):
        if engines and engine_dir.name not in engines:
            continue
        pages = errors = 0
        seconds: list[float] = []
        types: Counter = Counter()
        for path in engine_dir.glob("*/*.json"):
            r = read_result(path)
            pages += 1
            if r.status == "error":
                errors += 1
                continue
            seconds.append(r.seconds)
            types.update(b.type for b in r.blocks)
        median = f"{statistics.median(seconds):.1f}" if seconds else "-"
        longest = f"{max(seconds):.1f}" if seconds else "-"
        rows.append((engine_dir.name, pages, errors, median, longest, ", ".join(f"{t} {n}" for t, n in sorted(types.items()))))
    if not rows:
        return "no results"
    head = f"{'engine':<9} {'pages':>5} {'errors':>6} {'median_s':>8} {'max_s':>7}  blocks by type"
    lines = [f"{e:<9} {p:>5} {er:>6} {m:>8} {mx:>7}  {t}" for e, p, er, m, mx, t in rows]
    return "\n".join([head, *lines])
