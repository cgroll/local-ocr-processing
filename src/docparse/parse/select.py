"""Which pages to process: manifest entries restricted to page_range, with an intact local file."""
from dataclasses import dataclass
from pathlib import Path

from ..dataset.download import sha256_of
from ..dataset.manifest import Entry

RAW_DIR = Path("data/raw")


@dataclass
class DocPages:
    doc_id: str
    pdf_path: Path
    pages: list[int]  # 1-based


def entry_pages(entry: Entry) -> list[int]:
    if entry.page_range:
        first, last = (int(x) for x in entry.page_range.split("-"))
        return list(range(first, last + 1))
    return list(range(1, int(entry.pages or 0) + 1))


def select_pages(
    entries: list[Entry], raw_dir: Path = RAW_DIR, only: set[str] | None = None, limit: int | None = None,
) -> tuple[list[DocPages], list[str]]:
    """Returns (documents with pages, skip messages). `limit` caps the total number of pages."""
    selected, skipped = [], []
    remaining = limit
    for e in entries:
        if only is not None and e.id not in only:
            continue
        if remaining is not None and remaining <= 0:
            break
        pdf = raw_dir / e.id / "document.pdf"
        if not pdf.exists():
            skipped.append(f"{e.id}: file missing ({pdf})")
            continue
        if e.sha256 and sha256_of(pdf) != e.sha256:
            skipped.append(f"{e.id}: file does not match manifest sha256")
            continue
        pages = entry_pages(e)
        if remaining is not None:
            pages = pages[:remaining]
            remaining -= len(pages)
        if pages:
            selected.append(DocPages(e.id, pdf, pages))
    if only:
        for missing in sorted(only - {e.id for e in entries}):
            skipped.append(f"{missing}: not in manifest")
    return selected, skipped
