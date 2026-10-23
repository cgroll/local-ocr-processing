"""Candidate adapters: each finds documents in one source and returns manifest-shaped entries.

Candidates are written to data/candidates/<source>.csv and only enter the manifest through
the explicit `add` command.
"""
import re
from pathlib import Path

from ..manifest import Entry, save

CANDIDATES_DIR = Path("data/candidates")


def slug(text: str, max_len: int = 48) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len].strip("-")


def tag_string(tags: str | list[str]) -> str:
    items = tags.split(";") if isinstance(tags, str) else tags
    return ";".join(t.strip() for t in items if t.strip())


def write_candidates(source: str, entries: list[Entry], directory: Path = CANDIDATES_DIR) -> Path:
    path = directory / f"{source}.csv"
    save(entries, path)
    return path
