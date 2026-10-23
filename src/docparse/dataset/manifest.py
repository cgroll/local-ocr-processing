"""Dataset manifest: one CSV row per document, loaded, validated and saved here."""
import csv
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_PATH = Path("datasets/manifest.csv")

GROUPS = ("datasheet", "report", "scan", "corpus-sample")
RIGHTS = ("public-domain", "open-license", "vendor-copyright", "unknown")
KINDS = ("native", "scanned", "mixed")

# Fields that must be set as soon as an entry is in the manifest.
REQUIRED = ("id", "url", "group", "rights", "rights_source", "tags")
# Fields filled in at first download; required once the entry counts as verified.
VERIFIED = ("kind", "pages", "sha256")


@dataclass
class Entry:
    id: str = ""
    url: str = ""
    group: str = ""
    rights: str = ""
    rights_source: str = ""
    tags: str = ""  # ';'-separated
    title: str = ""
    kind: str = ""
    pages: str = ""
    page_range: str = ""  # optional "first-last" (1-based, inclusive)
    sha256: str = ""
    notes: str = ""

    @property
    def tag_list(self) -> list[str]:
        return [t for t in self.tags.split(";") if t]

    @property
    def page_count(self) -> int:
        """Pages in scope: the length of page_range if set, else all pages of the file."""
        if self.page_range:
            first, last = (int(x) for x in self.page_range.split("-"))
            return last - first + 1
        return int(self.pages) if self.pages else 0


COLUMNS = [f.name for f in fields(Entry)]


def load(path: Path = DEFAULT_PATH) -> list[Entry]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [Entry(**{c: (row.get(c) or "").strip() for c in COLUMNS}) for row in reader]


def save(entries: list[Entry], path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for e in entries:
            writer.writerow({c: getattr(e, c) for c in COLUMNS})
    tmp.replace(path)


def validate(entries: list[Entry], require_verified: bool = False) -> list[str]:
    """Return error messages; line numbers refer to the CSV file (header is line 1)."""
    errors = []
    seen: dict[str, int] = {}
    required = REQUIRED + (VERIFIED if require_verified else ())
    for i, e in enumerate(entries):
        line = i + 2
        for name in required:
            if not getattr(e, name):
                errors.append(f"line {line}: field '{name}' is missing (id={e.id or '?'})")
        if e.id:
            if e.id in seen:
                errors.append(f"line {line}: duplicate id '{e.id}' (first on line {seen[e.id]})")
            seen.setdefault(e.id, line)
        if e.group and e.group not in GROUPS:
            errors.append(f"line {line}: field 'group' has unknown value '{e.group}'")
        if e.rights and e.rights not in RIGHTS:
            errors.append(f"line {line}: field 'rights' has unknown value '{e.rights}'")
        if e.kind and e.kind not in KINDS:
            errors.append(f"line {line}: field 'kind' has unknown value '{e.kind}'")
        if e.pages and not e.pages.isdigit():
            errors.append(f"line {line}: field 'pages' is not a number: '{e.pages}'")
    return errors
