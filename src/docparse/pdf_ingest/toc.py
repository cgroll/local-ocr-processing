"""Table of contents: PDF bookmarks, a printed contents list read by a model, or headings.

The model (called by `kh-ingestion`, not here) only reads text into entries. Every entry is checked
here against the text of the page it names (after `verify_toc.py` in bezahlbarer-wohnraum):
the title must stand on that page or a neighbour; the offset printed page -> PDF page is measured
from the text, per kind of entry and section by section (journal extracts, roman front matter).
"""
import difflib
import re
from collections import Counter
from dataclasses import dataclass, field

import pymupdf

MIN_PAGES = 10  # shorter documents get no table of contents
CANDIDATE_PAGES = 15  # the first pages searched for a printed contents list
CANDIDATE_CHARS = 5000  # per page offered
CONTENTS_LINES = 5  # a page with this many "title ... 12" lines looks like a contents list
MIN_BOOKMARKS = 4
NEIGHBOURS = 2
OK_SHARE = 0.5
MIN_ENTRIES = 3
MAX_HEADING_ENTRIES = 150
KINDS = ("chapter", "figure", "table")


@dataclass
class Entry:
    title: str
    pdf_page: int
    level: int = 1
    kind: str = "chapter"
    number: str = ""
    printed_page: int | None = None
    verified: bool = True


@dataclass
class Toc:
    source: str  # bookmarks | printed_toc | headings | none
    entries: list[Entry] = field(default_factory=list)

    @property
    def confirmed(self) -> int:
        return sum(1 for e in self.entries if e.verified)


def norm(s: str) -> str:
    s = s.lower().replace("ß", "ss")
    s = re.sub(r"-\s*\n\s*", "", s)
    return re.sub(r"[^a-z0-9äöü]+", "", s)


def title_in(title: str, page_norm: str) -> bool:
    t = norm(title)
    if len(t) < 4:
        return False
    if t in page_norm:
        return True
    head = t[:40]
    if len(head) < 15:
        return False
    blocks = difflib.SequenceMatcher(None, page_norm, head, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks if b.size >= 4) >= int(len(head) * 0.9)


def bookmark_entries(doc: pymupdf.Document) -> list[Entry]:
    out = []
    for level, title, page in doc.get_toc(simple=True):
        title = " ".join(str(title).split())
        if title and 1 <= page <= len(doc):
            out.append(Entry(title, page, level=max(1, min(level, 6))))
    # one single-word bookmark per page is a file label ("scan_0001_a"), not a table of contents
    if len(out) >= 0.9 * len(doc) and all(" " not in e.title for e in out):
        return []
    # a handful of bookmarks in a long document is not its structure: the printed list is better
    if len(doc) >= MIN_PAGES and len(out) < max(MIN_BOOKMARKS, len(doc) / 15):
        return []
    return out


_CONTENTS_LINE = re.compile(r"(?:\.{3,}|\s{2,}|\s)\d{1,4}\s*$")


def looks_like_contents(text: str) -> bool:
    lines = [l for l in text.splitlines() if l.strip()]
    return sum(1 for l in lines if _CONTENTS_LINE.search(l) and len(l.strip()) > 6) >= CONTENTS_LINES


def candidate_pages(texts: dict[int, str]) -> list[dict]:
    """Text of the pages offered to the model: those among the first pages that look like a list of
    titles with page numbers, each with its neighbours (a list often runs over two pages), and the two or three pages before the first one. Without
    such a page nothing is offered, and the model only sees the headings."""
    first = sorted(texts)[:CANDIDATE_PAGES]
    hits = sorted(p for p in first if looks_like_contents(texts[p]))
    near = {q for p in hits for q in (p - 1, p, p + 1)}
    if hits:  # the list often starts on a page whose own lines do not look like entries (long wrapped titles)
        near |= {hits[0] - 2, hits[0] - 3}
    chosen = sorted(q for q in near if q in first and texts[q].strip())
    return [{"page": p, "text": texts[p][:CANDIDATE_CHARS]} for p in chosen]


def _clean(raw: list[dict], use_pdf_page: bool) -> list[Entry]:
    out = []
    for r in raw or []:
        try:
            title = " ".join(str(r["title"]).split())
            page = r.get("pdf_page") if use_pdf_page else r.get("printed_page")
            kind = r.get("kind") if r.get("kind") in KINDS else "chapter"
            if not title or page is None:
                continue
            e = Entry(title, int(page), level=max(1, min(int(r.get("level") or 1), 6)), kind=kind,
                      number=str(r.get("number") or "").strip(), printed_page=None if use_pdf_page else int(page), verified=False)
            out.append(e)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def verify(raw: list[dict], texts: dict[int, str], n_pages: int, use_pdf_page: bool = False,
           toc_pages: set[int] | None = None) -> Toc | None:
    """Entries with PDF pages and `verified` flags; None when fewer than half are confirmed or
    there are too few entries to be a contents list."""
    entries = _clean(raw, use_pdf_page)
    if len(entries) < MIN_ENTRIES:
        return None
    normed = {p: norm(t) for p, t in texts.items()}
    found = [[p for p in sorted(normed) if title_in(e.title, normed[p])] for e in entries]
    if toc_pages is None:  # not named by the reader: pages where more than half of the titles appear
        per_page = Counter(p for f in found for p in f)
        toc_pages = {p for p, c in per_page.items() if c >= max(5, 0.5 * len(entries)) and p <= max(30, n_pages // 4)}
    found = [[p for p in f if p not in toc_pages] for f in found]

    if use_pdf_page:
        for e, f in zip(entries, found):
            near = [p for p in f if abs(p - e.pdf_page) <= NEIGHBOURS]
            e.verified = bool(near)
            e.pdf_page = min(near, key=lambda p: abs(p - e.pdf_page)) if near else min(max(e.pdf_page, 1), n_pages)
    else:
        offsets = Counter(p - e.printed_page for e, f in zip(entries, found) if len(f) <= 3 for p in f)
        start = offsets.most_common(1)[0][0] if offsets else 0
        for kind in KINDS:
            idx = [i for i, e in enumerate(entries) if e.kind == kind]
            prev, cur = 1, start
            for i in idx:
                e, f = entries[i], [p for p in found[i] if p >= prev]
                expected = e.printed_page + cur
                near = [p for p in f if abs(p - expected) <= NEIGHBOURS]
                if near:
                    pick = min(near, key=lambda p: abs(p - expected))
                elif len(f) == 1:  # section with another offset
                    pick = f[0]
                else:
                    pick = None
                if pick is not None:
                    e.verified, e.pdf_page = True, pick
                    cur, prev = pick - e.printed_page, pick
                else:
                    e.pdf_page = min(max(expected, prev), n_pages)
    toc = Toc("printed_toc", entries)
    return toc if toc.confirmed >= OK_SHARE * len(entries) else None


def heading_entries(headings: list[dict]) -> list[Entry]:
    """Entries from detected headings (`level`, `text`, `page`); running heads that repeat are dropped."""
    pages_of: dict[str, set[int]] = {}
    for h in headings:
        pages_of.setdefault(norm(h["text"]), set()).add(h["page"])
    out = [Entry(" ".join(h["text"].split()), h["page"], level=h["level"]) for h in headings
           if len(pages_of[norm(h["text"])]) < 3 and norm(h["text"])]
    if len(out) > MAX_HEADING_ENTRIES:
        out = [e for e in out if e.level <= 2]
    return out


def choose(
    n_pages: int, bookmarks: list[Entry], model: dict | None, headings: list[dict], texts: dict[int, str],
) -> Toc:
    """Rank: bookmarks, then the printed list (read by the model), then headings."""
    if n_pages < MIN_PAGES:
        return Toc("none")
    if bookmarks:
        return Toc("bookmarks", bookmarks)
    model = model or {}
    listed = {p for p in model.get("toc_pages") or [] if isinstance(p, int)} or None
    toc = verify(model.get("printed_toc") or [], texts, n_pages, toc_pages=listed)
    if toc is not None:
        return toc
    if model.get("headings"):
        toc = verify(model["headings"], texts, n_pages, use_pdf_page=True)
        if toc is not None:
            toc.source = "headings"
            return toc
    entries = heading_entries(headings)
    return Toc("headings", entries) if len(entries) >= MIN_ENTRIES else Toc("none")


def render(toc: Toc) -> str:
    """Markdown sections `## Inhaltsverzeichnis`, `## Abbildungen`, `## Tabellen` ("" for none)."""
    if toc.source == "none" or not toc.entries:
        return ""

    def line(e: Entry, indent: int) -> str:
        num = f"{e.number} " if e.number else ""
        extra = f" (gedruckt {e.printed_page})" if e.printed_page and e.printed_page != e.pdf_page else ""
        return f"{'  ' * indent}- {num}{e.title} · S. {e.pdf_page}{extra}{'' if e.verified else ' ?'}"

    sections = []
    chapters = [e for e in toc.entries if e.kind == "chapter"]
    if chapters:
        low = min(e.level for e in chapters)
        body = "\n".join(line(e, min(e.level - low, 4)) for e in chapters)
        sections.append(
            "## Inhaltsverzeichnis\n\n*Seitenzahlen sind PDF-Seiten (`## Seite N`); `?` = Titel auf der Seite nicht bestätigt.*\n\n" + body
        )
    for kind, title in (("figure", "Abbildungen"), ("table", "Tabellen")):
        es = [e for e in toc.entries if e.kind == kind]
        if es:
            sections.append(f"## {title}\n\n" + "\n".join(line(e, 0) for e in es))
    return "\n\n".join(sections)
