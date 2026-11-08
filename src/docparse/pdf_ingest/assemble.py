"""Pages of one PDF as content items (headings, paragraphs, figures, tables) in reading order.

Pure with respect to the media folder: visual items only name the page image and the box to crop;
`render.py` writes the files. Text comes from the `pymupdf` result, scanned pages from `ocr`;
with a `layout` result the reading order, headers/footers, figures, charts and tables come from it.
"""
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..digest import markdown as M
from ..digest.page import _assign_captions
from ..enrich import blocks as B
from ..parse.format import Block, PageResult
from . import textlayer as T

MIN_IMAGE_AREA_PX = B.MIN_VISUAL_AREA_PX
FULL_PAGE_RATIO = 0.85  # an image covering this much of the page is the page itself (scan, background)
ZONE_RATIO = 0.12  # top/bottom strip where headers, footers and page numbers sit
FURNITURE_PAGE_SHARE = 0.5
PRINTED_MIN_PAGES = 3
NO_JOIN_AFTER_HYPHEN = ("und ", "oder ", "bzw.", "sowie ", "and ", "or ")
TABLE_HINT = "*Tabelle automatisch erkannt, Zeilen und Spalten unverifiziert (verbundene Zellen); bei Zahlen die Abbildung oder die PDF-Seite ansehen.*"
FRAGMENT_CHARS = 600
DOC_ID = "doc"


@dataclass
class Item:
    kind: str  # heading | para | image | visual
    text: str = ""
    level: int = 1  # headings: 1..3
    bbox: list[float] = field(default_factory=list)
    vtype: str = ""  # visual: figure | chart | table
    caption: str = ""
    table_md: str = ""
    fragments: str = ""  # text found inside a figure/chart (axis labels, component values)
    index: int = 0  # n-th visual/image on the page, for file names


@dataclass
class PageContent:
    page: int
    items: list[Item] = field(default_factory=list)
    printed: int | None = None
    ocr: bool = False

    def text(self) -> str:
        parts = []
        for it in self.items:
            parts += [it.text, it.caption, it.table_md, it.fragments]
        return "\n".join(p for p in parts if p)


_BULLET = re.compile(r"^(?:[•▪◦●■◆▶►]|[-–—] |\d{1,2}[.)] )")


def join_lines(text: str) -> str:
    """Lines of one block to one paragraph line; hyphenation at a line end is resolved. A line that
    starts with a bullet or number marker starts a new line (list items stay separate)."""
    lines = [T.plain(l) for l in text.split("\n")]
    lines = [l for l in lines if l]
    out = ""
    for line in lines:
        if not out:
            out = line
        elif _BULLET.match(line):
            out += "\n" + line
        elif out.endswith("-") and len(out) > 1 and out[-2].isalpha() and line[:1].islower() \
                and not line.startswith(NO_JOIN_AFTER_HYPHEN):
            out = out[:-1] + line
        else:
            out += " " + line
    return out


def _is_title(b: Block) -> bool:
    return b.type == "title"


def _level(b: Block) -> int:
    m = re.fullmatch(r"h([1-3])", b.label or "")
    return int(m.group(1)) if m else 1


def merge_ocr_lines(blocks: list[Block]) -> list[Block]:
    """OCR delivers one block per text line; lines that follow each other closely and overlap
    horizontally become one paragraph block (in the given order)."""
    out: list[Block] = []
    for b in blocks:
        if b.type != "line" or not (b.text or "").strip() or not out or out[-1].type != "line":
            out.append(replace(b))
            continue
        prev = out[-1]
        height = max(1.0, min(prev.bbox[3] - prev.bbox[1], b.bbox[3] - b.bbox[1]))
        gap = b.bbox[1] - prev.bbox[3]
        overlap = min(prev.bbox[2], b.bbox[2]) - max(prev.bbox[0], b.bbox[0])
        if -0.2 * height <= gap <= 0.6 * height and overlap > 0:
            prev.text = f"{prev.text}\n{b.text}"
            prev.bbox = [min(prev.bbox[0], b.bbox[0]), min(prev.bbox[1], b.bbox[1]),
                         max(prev.bbox[2], b.bbox[2]), max(prev.bbox[3], b.bbox[3])]
        else:
            out.append(replace(b))
    return out


def _norm_key(text: str) -> str:
    return re.sub(r"\d+", "#", T.plain(text).lower())


def _zone(b: Block, height: float) -> str | None:
    if b.bbox[3] <= ZONE_RATIO * height:
        return "top"
    if b.bbox[1] >= (1 - ZONE_RATIO) * height:
        return "bottom"
    return None


def furniture_keys(pages: dict[int, PageResult]) -> set[tuple[str, str]]:
    """(zone, normalised text) of blocks that repeat in the top/bottom strip of at least half of
    the pages: running heads, footers and page numbers. Only for documents of 4+ pages."""
    if len(pages) < 4:
        return set()
    seen: Counter = Counter()
    for res in pages.values():
        keys = {(z, _norm_key(b.text)) for b in res.blocks if b.type == "text" and b.text
                and (z := _zone(b, res.height))}
        seen.update(keys)
    return {k for k, n in seen.items() if n >= max(3, FURNITURE_PAGE_SHARE * len(pages))}


_PAGE_NO = re.compile(r"^(?:seite|page|s\.|p\.)?\s*[-–—]?\s*(\d{1,4})\s*[-–—]?(?:\s*(?:/|von|of)\s*\d{1,4})?$", re.I)


def printed_numbers(res: PageResult) -> list[int]:
    """Numbers that look like a printed page number in the top/bottom strip."""
    out = []
    for b in res.blocks:
        if b.type in ("text", "line") and b.text and _zone(b, res.height):
            m = _PAGE_NO.match(T.plain(b.text))
            if m:
                out.append(int(m.group(1)))
    return out


def printed_pages(candidates: dict[int, list[int]]) -> dict[int, int]:
    """PDF page -> printed page number, where the numbers follow one consistent offset (at least on
    three pages and half of the pages that show a number)."""
    offsets = Counter(n - p for p, ns in candidates.items() for n in set(ns))
    if not offsets:
        return {}
    offset, count = offsets.most_common(1)[0]
    with_numbers = sum(1 for ns in candidates.values() if ns)
    if count < PRINTED_MIN_PAGES or count < 0.5 * with_numbers:
        return {}
    return {p: p + offset for p, ns in candidates.items() if p + offset in ns and p + offset >= 1}


def drop_empty_columns(md: str) -> str:
    """Markdown table without columns whose cells are all empty (the table finder often reports
    spurious ones for ruled tables)."""
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in md.splitlines() if line.strip()]
    if len(rows) < 2 or len({len(r) for r in rows}) != 1:
        return md
    body = [r for i, r in enumerate(rows) if i != 1]  # row 1 is the separator
    keep = [j for j in range(len(rows[0])) if any(r[j] for r in body)]
    if len(keep) == len(rows[0]) or not keep:
        return md
    return "\n".join("| " + " | ".join(r[j] for j in keep) + " |" for r in rows)


def _table_markdown(html: str | None, text: str | None) -> str:
    md = M.html_table_to_markdown(html) if html else ""
    return drop_empty_columns(md) if md else ""


def _drop_furniture(blocks: list[Block], res: PageResult, layout: PageResult | None, keys: set) -> list[Block]:
    if layout is not None:
        boxes = [r.bbox for r in layout.blocks if r.type in ("header", "footer")]
        blocks = [b for b in blocks if not any(B._inside(b.bbox, hb) >= 0.5 for hb in boxes)]
    return [b for b in blocks if not (b.type in ("text", "line") and b.text
                                      and (z := _zone(b, res.height)) and (z, _norm_key(b.text)) in keys)]


def _page_images(pymupdf_res: PageResult | None, furniture_xrefs_ok: bool = True) -> list[Block]:
    if pymupdf_res is None:
        return []
    page_area = pymupdf_res.width * pymupdf_res.height
    out = []
    for b in pymupdf_res.blocks:
        if b.type != "image":
            continue
        area = (b.bbox[2] - b.bbox[0]) * (b.bbox[3] - b.bbox[1])
        if area >= MIN_IMAGE_AREA_PX and area < FULL_PAGE_RATIO * page_area:
            out.append(b)
    return out


def build_page(
    page: int, results: Path, use_layout: bool, keys: set, printed: dict[int, int],
    repeated_images: set[tuple[int, int, int, int]] | None = None,
) -> PageContent:
    pymu = B.read_ok("pymupdf", DOC_ID, page, results)
    layout = B.read_ok("layout", DOC_ID, page, results) if use_layout else None
    name, source = B.choose_text_source(DOC_ID, page, results)
    content = PageContent(page, printed=printed.get(page), ocr=name == "ocr")
    if source is None and layout is None:
        return content

    visuals = B.visual_candidates(layout) if layout is not None else []
    narrative: list[Block] = []
    if source is not None:  # a page of only a table or figure has no text source, but still its visuals
        narrative = B.narrative_blocks(source, [v.bbox for v in visuals], layout)
        narrative = [b for b in narrative if b.type not in ("image", "drawing")]  # no text; images come in below
        narrative = _drop_furniture(narrative, source, layout, keys)
        if name == "ocr":
            narrative = merge_ocr_lines(narrative)
    height = source.height if source is not None else layout.height

    captions = _assign_captions(visuals, layout, narrative, height) if layout is not None else {}
    consumed = set().union(*(ids for _, ids in captions.values())) if captions else set()
    narrative = [b for b in narrative if id(b) not in consumed]
    # text inside a figure/chart (or a table without Markdown) is not running text: it is kept as one line
    inside: dict[int, list[str]] = {i: [] for i in range(len(visuals))}
    rest = []
    for b in narrative:
        owner = next((i for i, v in enumerate(visuals) if B._inside(b.bbox, v.bbox) >= 0.5), None)
        if owner is None or not (b.text or "").strip():
            rest.append(b)
        else:
            inside[owner].append(T.plain(b.text))
    narrative = rest

    extras: list[tuple] = []
    for vi, v in enumerate(visuals):
        table_md = ""
        if v.type == "table" and pymu is not None:
            for t in (b for b in pymu.blocks if b.type == "table" and b.html):
                if B._inside(t.bbox, v.bbox) >= 0.5:
                    table_md = _table_markdown(t.html, t.text)
                    break
        frag = ""
        if not table_md:
            frag = ", ".join(dict.fromkeys(inside[vi]))
            frag = frag[:FRAGMENT_CHARS].rsplit(", ", 1)[0] + ", …" if len(frag) > FRAGMENT_CHARS else frag
        item = Item("visual", bbox=list(v.bbox), vtype=v.type, caption=captions.get(vi, ("", set()))[0],
                    table_md=table_md, fragments=frag)
        extras.append(("v", item, v.bbox))
    if layout is None and name != "ocr":
        for b in _page_images(pymu):
            key = tuple(round(x / 10) for x in b.bbox)
            if repeated_images and key in repeated_images:
                continue
            extras.append(("v", Item("image", bbox=list(b.bbox)), b.bbox))

    entries = [("n", b, b.bbox) for b in narrative]
    for kind, payload, _ in B.insert_by_position(entries, extras):
        if kind == "v":
            content.items.append(payload)
            continue
        b: Block = payload
        if b.type == "table":
            md = _table_markdown(b.html, b.text)
            if md:
                content.items.append(Item("para", text=f"{md}\n\n{TABLE_HINT}"))
                continue
        text = join_lines(b.text or b.markdown or "")
        if not text:
            continue
        if _is_title(b):
            content.items.append(Item("heading", text=text, level=_level(b), bbox=list(b.bbox)))
        elif b.type == "list":
            content.items.append(Item("para", text="\n".join(f"- {join_lines(l)}" for l in (b.text or "").splitlines() if l.strip())))
        else:
            content.items.append(Item("para", text=text, bbox=list(b.bbox)))
    n = Counter()
    for it in content.items:
        if it.kind in ("visual", "image"):
            n[it.kind] += 1
            it.index = sum(n.values())
    return content


def repeated_image_boxes(pages: dict[int, PageResult]) -> set[tuple[int, int, int, int]]:
    """Image boxes (rounded to 10 px) that recur on at least half of the pages: logos, backgrounds."""
    if len(pages) < 4:
        return set()
    seen: Counter = Counter()
    for res in pages.values():
        seen.update({tuple(round(x / 10) for x in b.bbox) for b in res.blocks if b.type == "image"})
    return {k for k, c in seen.items() if c >= max(3, FURNITURE_PAGE_SHARE * len(pages))}


def build_pages(results: Path, n_pages: int, use_layout: bool) -> list[PageContent]:
    pymu = {p: r for p in range(1, n_pages + 1) if (r := B.read_ok("pymupdf", DOC_ID, p, results))}
    ocr = {p: r for p in range(1, n_pages + 1) if (r := B.read_ok("ocr", DOC_ID, p, results))}
    # per page the result the text comes from: the text layer, or OCR for scanned pages
    text_res = {p: (pymu[p] if p in pymu and any(b.text for b in pymu[p].blocks) else ocr.get(p, pymu.get(p)))
                for p in range(1, n_pages + 1)}
    text_res = {p: r for p, r in text_res.items() if r is not None}
    keys = furniture_keys(text_res)
    printed = printed_pages({p: printed_numbers(r) for p, r in text_res.items()})
    rep = repeated_image_boxes(pymu)
    return [build_page(p, results, use_layout, keys, printed, rep) for p in range(1, n_pages + 1)]
