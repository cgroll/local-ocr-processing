"""Collect what the viewer shows: per-page results of all engines and per-document coverage."""
import json
from dataclasses import dataclass
from pathlib import Path

from ..dataset.manifest import Entry
from ..parse.format import RESULTS_DIR, read_result, result_path
from .sanitize import sanitize_table

ENGINES = ("pymupdf", "layout", "ocr", "vl")


def page_numbers(entry: Entry) -> list[int]:
    """1-based pages in scope for a manifest entry."""
    if entry.page_range:
        first, last = (int(x) for x in entry.page_range.split("-"))
        return list(range(first, last + 1))
    return list(range(1, int(entry.pages or 0) + 1))


def embed_json(obj) -> str:
    """JSON safe inside a <script> block: no '<' left, so '</script>' and '<!--' cannot occur."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _load_engine(engine: str, doc_id: str, page: int, results_dir: Path) -> dict:
    path = result_path(engine, doc_id, page, results_dir)
    if not path.exists():
        return {"state": "missing"}
    try:
        result = read_result(path)
    except (OSError, ValueError, TypeError, KeyError) as e:
        return {"state": "error", "error": f"result file unreadable: {e}"}
    if result.status == "error":
        return {"state": "error", "error": result.error or "unknown error"}
    blocks = []
    for i, b in enumerate(result.blocks):
        d = {k: v for k, v in vars(b).items() if v is not None}
        if "html" in d:
            d["html"] = sanitize_table(d["html"])
        d["id"] = f"{engine}:{i}"
        blocks.append(d)
    return {
        "state": "ok", "seconds": result.seconds, "version": result.engine_version,
        "size": [result.width, result.height], "blocks": blocks,
    }


def page_data(entry: Entry, page: int, results_dir: Path = RESULTS_DIR) -> dict:
    """All engine results of one page; failed and absent results are marked, tables are sanitized."""
    engines = {e: _load_engine(e, entry.id, page, results_dir) for e in ENGINES}
    size = next((r["size"] for r in engines.values() if r["state"] == "ok"), None)
    return {
        "doc": entry.id, "title": entry.title or entry.id, "page": page,
        "size": size, "engines": engines,
    }


@dataclass
class DocCoverage:
    entry: Entry
    pages: list[int]  # pages in scope
    counts: dict[str, dict[str, int]]  # engine -> {ok, error, missing}
    with_results: list[int]  # pages that have a result from at least one engine


def coverage(entry: Entry, results_dir: Path = RESULTS_DIR) -> DocCoverage:
    pages = page_numbers(entry)
    counts = {e: {"ok": 0, "error": 0, "missing": 0} for e in ENGINES}
    with_results = []
    for p in pages:
        found = False
        for e in ENGINES:
            path = result_path(e, entry.id, p, results_dir)
            if not path.exists():
                counts[e]["missing"] += 1
                continue
            found = True
            try:
                ok = read_result(path).status == "ok"
            except (OSError, ValueError, TypeError, KeyError):
                ok = False
            counts[e]["ok" if ok else "error"] += 1
        if found:
            with_results.append(p)
    return DocCoverage(entry, pages, counts, with_results)


def index_data(entries: list[Entry], results_dir: Path = RESULTS_DIR) -> list[DocCoverage]:
    """Coverage of every document that has at least one result, in manifest order."""
    return [c for c in (coverage(e, results_dir) for e in entries) if c.with_results]
