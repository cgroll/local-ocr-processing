"""PDF -> Markdown plus media in two stages (see `__main__` for the command contract).

`extract` reads the text layer, finds scanned pages, runs the layout model on all pages and OCR on
scanned ones (one model at a time) and leaves everything in `<out>/_work`. `render` assembles
`document.md`, `media/` and `run.json` from that, with a table of contents.
"""
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pymupdf
from PIL import Image

from ..enrich import blocks as B
from ..models import Registry
from ..parse.format import write_result
from ..parse.render import DEFAULT_DPI
from ..parse.runner import default_executor, run_engine
from ..parse.select import DocPages
from . import assemble as A
from . import textlayer as T
from . import toc as TOC

MAX_PAGES = 500
EXIT_INPUT = 2


class InputError(ValueError):
    """The PDF cannot be processed (not a PDF, encrypted, too large); no output is wanted."""


@dataclass
class Options:
    layout: bool = True
    ocr: str = "auto"  # auto | off
    executor_factory: Callable | None = None  # tests inject fake engines
    registry: Registry | None = None


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def open_pdf(pdf: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(pdf)
    except Exception as e:
        raise InputError(f"not a readable PDF: {e}") from e
    if not doc.is_pdf:
        raise InputError("not a PDF file")
    if doc.needs_pass:
        raise InputError("the PDF is encrypted (needs a password)")
    if len(doc) == 0:
        raise InputError("the PDF has no pages")
    if len(doc) > MAX_PAGES:
        raise InputError(f"the PDF has {len(doc)} pages, the limit is {MAX_PAGES}")
    return doc


def work_dir(out: Path) -> Path:
    return out / "_work"


def _run(key: str, pages: list[int], pdf: Path, work: Path, opts: Options) -> tuple[int, str | None]:
    """Run one engine over `pages`; returns (pages with an error, first error message)."""
    factory = opts.executor_factory or default_executor
    registry = opts.registry or Registry.load(None)
    counts = run_engine(
        key, [DocPages(A.DOC_ID, pdf, pages)], registry, dpi=DEFAULT_DPI, results_dir=work / "results",
        pages_dir=work / "pages", executor_factory=factory,
        log=lambda m: log(f"progress {m}"),
    )
    return counts.errors, (counts.messages[0] if counts.messages else None)


def heading_list(pages: list[A.PageContent]) -> list[dict]:
    return [{"level": it.level, "text": it.text, "page": pc.page} for pc in pages for it in pc.items if it.kind == "heading"]


def extract(pdf: Path, out: Path, opts: Options) -> dict:
    t0 = time.perf_counter()
    doc = open_pdf(pdf)
    n = len(doc)
    work = work_dir(out)
    (work / "results").mkdir(parents=True, exist_ok=True)

    body = T.body_font_size(doc)
    levels = T.heading_sizes(doc, body)
    scan_pages = []
    for i in range(n):
        write_result(T.extract_page(doc, i, A.DOC_ID, body, levels), work / "results")
        if T.is_scan(doc[i]):
            scan_pages.append(i + 1)
        if (i + 1) % 25 == 0 or i + 1 == n:
            log(f"progress text {i + 1}/{n}")
    meta = doc.metadata or {}
    bookmarks = TOC.bookmark_entries(doc)
    doc.close()

    state: dict = {
        "pages": n, "ocr_pages": [], "layout": False, "layout_error": None, "ocr_error": None,
        "scan_pages": scan_pages, "metadata": {k: meta.get(k) or "" for k in ("title", "author", "creationDate")},
        "bookmarks": [vars(e) for e in bookmarks], "body_font": body, "pymupdf": pymupdf.__version__,
    }
    if opts.layout:
        errors, msg = _run("layout", list(range(1, n + 1)), pdf, work, opts)
        state["layout"] = errors < n
        if errors:
            state["layout_error"] = msg
    if scan_pages and opts.ocr != "off":
        errors, msg = _run("ocr", scan_pages, pdf, work, opts)
        state["ocr_pages"] = [p for p in scan_pages if B.read_ok("ocr", A.DOC_ID, p, work / "results")]
        if errors:
            state["ocr_error"] = msg

    pages = A.build_pages(work / "results", n, state["layout"])
    texts = {pc.page: pc.text() for pc in pages}
    candidates = {
        "n_pages": n, "bookmarks": state["bookmarks"], "pages": TOC.candidate_pages(texts), "headings": heading_list(pages),
    }
    (out / "toc_candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8")
    state["extract_seconds"] = round(time.perf_counter() - t0, 1)
    (work / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return state


_BAD_TITLE = ("microsoft word", "untitled", "unbenannt", "powerpoint")


def usable_title(title: str) -> str:
    t = " ".join((title or "").split())
    if not t or not any(c.isalpha() for c in t) or t.lower().endswith((".pdf", ".doc", ".docx", ".indd", ".tex", ".ppt", ".pptx", ".dvi")):
        return ""
    return "" if t.lower().startswith(_BAD_TITLE) else t


def created_date(raw: str) -> str:
    """PDF date `D:20230115...` as `YYYY-MM-DD`, or ''."""
    d = (raw or "").removeprefix("D:")
    if len(d) >= 8 and d[:8].isdigit() and 1900 <= int(d[:4]) <= 2100 and 1 <= int(d[4:6]) <= 12 and 1 <= int(d[6:8]) <= 31:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return ""


def _write_visual(page_png: Path, it: A.Item, page: int, media: Path) -> str | None:
    """Crop file name relative to `media/`, or None when the crop failed."""
    try:
        img = B.crop_region(page_png, it.bbox)
        ext = "jpg" if it.vtype == "figure" else "png"
        name = f"p{page:04d}_{it.index}.{ext}"
        media.mkdir(exist_ok=True)
        img.save(media / name, quality=85) if ext == "jpg" else img.save(media / name)
        return name
    except Exception as e:  # one bad crop must not stop the item
        log(f"warning: crop on page {page} failed: {e}")
        return None


def _write_embedded(pdf: Path, it: A.Item, page: int, media: Path, to_pixels_scale: float) -> str | None:
    try:
        with pymupdf.open(pdf) as doc:
            rect = pymupdf.Rect(it.bbox) * (1 / to_pixels_scale)
            pix = doc[page - 1].get_pixmap(clip=rect, dpi=200)
            name = f"p{page:04d}_{it.index}.png"
            media.mkdir(exist_ok=True)
            pix.save(media / name)
            return name
    except Exception as e:
        log(f"warning: image on page {page} failed: {e}")
        return None


COVER_WIDTH_PX = 600


def write_cover(pdf: Path, media: Path) -> bool:
    """First page as a small JPEG (`media/cover.jpg`), the thumbnail of the item's tile."""
    try:
        with pymupdf.open(pdf) as doc:
            page = doc[0]
            zoom = COVER_WIDTH_PX / max(page.rect.width, 1)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False)
            media.mkdir(exist_ok=True)
            pix.save(media / "cover.jpg", jpg_quality=80)
        return True
    except Exception as e:  # a missing thumbnail must not stop the item
        log(f"warning: cover image failed: {e}")
        return False


LABEL = {"figure": "Abbildung", "chart": "Diagramm", "table": "Tabelle", "image": "Bild"}


def page_markdown(pc: A.PageContent, pdf: Path, work: Path, out: Path) -> str:
    marker = f"## Seite {pc.page}" + (f" · gedruckt S. {pc.printed}" if pc.printed and pc.printed != pc.page else "")
    parts = [marker]
    media = out / "media"
    png = work / "pages" / A.DOC_ID / f"{pc.page:04d}.png"
    for it in pc.items:
        if it.kind == "heading":
            parts.append("#" * (2 + it.level) + " " + it.text)
        elif it.kind == "para":
            parts.append(it.text)
        else:
            kind = it.vtype if it.kind == "visual" else "image"
            name = _write_visual(png, it, pc.page, media) if it.kind == "visual" and png.exists() \
                else _write_embedded(pdf, it, pc.page, media, DEFAULT_DPI / 72) if it.kind == "image" else None
            block = []
            if name:
                block.append(f"![{LABEL.get(kind, 'Bild')} S. {pc.page}](media/{name})")
            if it.caption:
                block.append(f"*{it.caption}*")
            if it.table_md:
                block.append(it.table_md)
                block.append(A.TABLE_HINT)
            elif it.fragments:
                block.append(f"*Text im Bild:* {it.fragments}")
            if block:
                parts.append("\n\n".join(block))
    if len(parts) == 1:
        parts.append("*(kein Text erkannt)*")
    return "\n\n".join(parts)


def render(pdf: Path, out: Path, toc_file: Path | None = None) -> dict:
    t0 = time.perf_counter()
    work = work_dir(out)
    state = json.loads((work / "state.json").read_text(encoding="utf-8"))
    n = state["pages"]
    pages = A.build_pages(work / "results", n, state["layout"])
    texts = {pc.page: pc.text() for pc in pages}
    model = json.loads(toc_file.read_text(encoding="utf-8")) if toc_file else None
    bookmarks = [TOC.Entry(**b) for b in state["bookmarks"]]
    toc = TOC.choose(n, bookmarks, model, heading_list(pages), texts)

    old_media = out / "media"  # a second render must not leave crops of the first behind
    if old_media.exists():
        for f in old_media.iterdir():
            f.unlink()
    sections = []
    toc_md = TOC.render(toc)
    if toc_md:
        sections.append(toc_md)
    sections += [page_markdown(pc, pdf, work, out) for pc in pages]
    (out / "document.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    cover = write_cover(pdf, out / "media")

    meta = state["metadata"]
    first_heading = next((it.text for pc in pages[:1] for it in pc.items
                          if it.kind == "heading" and len(it.text) >= 4 and any(c.isalpha() for c in it.text)), "")
    run = {
        "pages": n,
        "title": usable_title(meta.get("title", "")) or first_heading,
        "author": " ".join((meta.get("author") or "").split()),
        "created": created_date(meta.get("creationDate", "")),
        "stage": "layout" if state["layout"] else "text",
        "cover": cover,
        "layout_error": state["layout_error"],
        "ocr_pages": state["ocr_pages"],
        "ocr_error": state["ocr_error"],
        "toc": {"source": toc.source, "entries": len(toc.entries), "confirmed": toc.confirmed,
                "model": (model or {}).get("model")},
        "printed_pages": {str(pc.page): pc.printed for pc in pages if pc.printed},
        "versions": {"pymupdf": state["pymupdf"]},
        "seconds": round(state.get("extract_seconds", 0) + time.perf_counter() - t0, 1),
    }
    (out / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    return run
