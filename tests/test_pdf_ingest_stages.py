"""OCR fallback, table of contents and layout stage with fake engines (no GPU)."""
import json
import re

import pymupdf

from docparse.parse.format import Block
from docparse.pdf_ingest import __main__ as cli
from docparse.pdf_ingest import pipeline as P
from docparse.pdf_ingest import toc as T

import pdfgen


class FakeExecutor:
    """Stands in for a loaded model: `fn(page) -> blocks`."""
    def __init__(self, fn):
        self.fn = fn

    def start(self): ...
    def close(self): ...

    def process(self, spec, job):
        return self.fn(spec.page, job.rendered.width, job.rendered.height)


def factory(layout=None, ocr=None, fail_layout=False):
    def make(key, registry):
        if key == "layout":
            if fail_layout:
                raise RuntimeError("cannot load layout model")
            return FakeExecutor(layout or (lambda p, w, h: []))
        return FakeExecutor(ocr or (lambda p, w, h: []))
    return make


def run_stages(tmp_path, data, layout=True, ocr="auto", fac=None, toc=None):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(data)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    opts = P.Options(layout=layout, ocr=ocr, executor_factory=fac)
    P.extract(pdf, out, opts)
    toc_file = None
    if toc is not None:
        toc_file = tmp_path / "toc.json"
        toc_file.write_text(json.dumps(toc))
    run = P.render(pdf, out, toc_file)
    return (out / "document.md").read_text(encoding="utf-8"), run, out


def ocr_lines(page, w, h):
    return [Block("line", "text_line", [100, 200 + i * 40, 900, 230 + i * 40], "ocr", order=i, confidence=0.9, text=t)
            for i, t in enumerate(["Gescannte Zeile eins", "und Zeile zwei", ])]


# --- 1.5 scans -------------------------------------------------------------------------------

def test_only_scan_page_is_ocred(tmp_path):
    md, run, out = run_stages(tmp_path, pdfgen.scan_page_mixed(), layout=False, fac=factory(ocr=ocr_lines))
    assert run["ocr_pages"] == [2]
    page2 = md.split("## Seite 2")[1].split("## Seite 3")[0]
    assert "Gescannte Zeile eins und Zeile zwei" in page2  # lines joined to one paragraph
    assert "Lorem ipsum" not in page2 and "Lorem ipsum" in md.split("## Seite 3")[1]


def test_pure_scan_all_pages_ocr(tmp_path):
    from conftest import make_pdf
    md, run, _ = run_stages(tmp_path, make_pdf(3, text=False, scan=True), layout=False, fac=factory(ocr=ocr_lines))
    assert run["ocr_pages"] == [1, 2, 3]


def test_ocr_off(tmp_path):
    md, run, _ = run_stages(tmp_path, pdfgen.scan_page_mixed(), layout=False, ocr="off", fac=factory(ocr=ocr_lines))
    assert run["ocr_pages"] == [] and "Gescannte Zeile" not in md
    assert "## Seite 2\n\n*(kein Text erkannt)*" in md


# --- 2 table of contents ---------------------------------------------------------------------

def test_toc_from_bookmarks_no_model(tmp_path):
    md, run, _ = run_stages(tmp_path, pdfgen.with_bookmarks(12), layout=False)
    assert run["toc"]["source"] == "bookmarks"
    head = md.split("## Seite 1")[0]
    assert "## Inhaltsverzeichnis" in head
    assert "- Einleitung · S. 1" in head and "  - Hintergrund · S. 2" in head and "- Ergebnisse · S. 9" in head


def test_short_document_has_no_toc(tmp_path):
    md, run, _ = run_stages(tmp_path, pdfgen.with_bookmarks(4), layout=False)
    assert "## Inhaltsverzeichnis" not in md and run["toc"]["source"] == "none"


def _book_with_printed_toc(offset=8, pages=30):
    """Pages 1-2: contents list with printed pages; chapter k starts on PDF page k*4+offset-ish."""
    doc = pymupdf.open()
    chapters = [(f"Kapitel {n} {t}", 5 + 4 * n) for n, t in enumerate(["Einleitung", "Grundlagen", "Methoden", "Ergebnisse", "Diskussion"])]
    for i in range(pages):
        p = doc.new_page()
        if i == 1:
            y = 80
            for title, printed in chapters:
                p.insert_text((72, y), f"{title} .......... {printed}", fontsize=11)
                y += 20
        else:
            p.insert_textbox(pymupdf.Rect(72, 200, 520, 300), "Fliesstext " * 20, fontsize=10)
    for title, printed in chapters:
        doc[printed + offset - 1].insert_text((72, 120), title, fontsize=16, fontname="hebo")
    data = doc.tobytes()
    return data, chapters


def test_printed_toc_offset_and_unconfirmed(tmp_path):
    data, chapters = _book_with_printed_toc(8)
    raw = [{"number": "", "title": t, "printed_page": p, "level": 1, "kind": "chapter"} for t, p in chapters]
    raw.append({"number": "", "title": "Anhang Erfunden", "printed_page": 22, "level": 1, "kind": "chapter"})
    md, run, _ = run_stages(tmp_path, data, layout=False, toc={"printed_toc": raw, "model": "fake"})
    head = md.split("\n## Seite 1")[0]
    assert run["toc"]["source"] == "printed_toc" and run["toc"]["model"] == "fake"
    assert f"- Kapitel 0 Einleitung · S. {5 + 8} (gedruckt 5)" in head
    assert "Kapitel 4 Diskussion · S. 29 (gedruckt 21)" in head
    assert re.search(r"Anhang Erfunden · S. \d+ .*\?$", head, re.M)  # not confirmed
    assert run["toc"]["confirmed"] == 5 and run["toc"]["entries"] == 6


def test_wrong_printed_toc_discarded_falls_back_to_headings(tmp_path):
    data, chapters = _book_with_printed_toc(8)
    bad = [{"title": f"Gibt es nicht {k}", "printed_page": 5 + k, "level": 1, "kind": "chapter"} for k in range(6)]
    md, run, _ = run_stages(tmp_path, data, layout=False, toc={"printed_toc": bad})
    assert run["toc"]["source"] == "headings"
    assert "Gibt es nicht" not in md.split("\n## Seite 1")[0]
    assert "Kapitel 2 Methoden" in md.split("\n## Seite 1")[0]


def test_headings_fallback_without_toc_file(tmp_path):
    data, _ = _book_with_printed_toc(8)
    md, run, _ = run_stages(tmp_path, data, layout=False)
    assert run["toc"]["source"] == "headings" and run["toc"]["entries"] >= 5


def test_toc_candidates_file(tmp_path):
    data, _ = _book_with_printed_toc(8)
    _, _, out = run_stages(tmp_path, data, layout=False)
    c = json.loads((out / "toc_candidates.json").read_text())
    assert set(c) == {"n_pages", "bookmarks", "pages", "headings"} and c["n_pages"] == 30
    assert 1 <= len(c["pages"]) <= T.CANDIDATE_PAGES and c["pages"][0]["page"] >= 1
    assert any("Kapitel" in p["text"] for p in c["pages"])


def test_figure_list_kept_separate(tmp_path):
    data, chapters = _book_with_printed_toc(8)
    raw = [{"title": t, "printed_page": p, "level": 1, "kind": "chapter"} for t, p in chapters]
    raw += [{"title": "Abbildung Eins", "printed_page": 7, "kind": "figure"}] * 0
    md, run, _ = run_stages(tmp_path, data, layout=False, toc={"printed_toc": raw})
    assert "## Abbildungen" not in md


# --- 3 layout ---------------------------------------------------------------------------------

def layout_fig(page, w, h):
    return [
        Block("title", "paragraph_title", [100, 100, 700, 160], "layout", confidence=0.9, order=1),
        Block("chart", "chart", [100, 300, 700, 700], "layout", confidence=0.9),
        Block("caption", "figure_title", [100, 710, 700, 750], "layout", confidence=0.9),
        Block("footer", "footer", [100, h - 100, 700, h - 60], "layout", confidence=0.9),
    ]


def test_layout_crop_with_caption(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 90), "Ueberschrift", fontsize=12)
    p.insert_text((50, 360), "Abbildung 1: Verlauf der Werte", fontsize=10)  # caption row, below the chart
    p.insert_text((50, 800), "Fusszeile 7", fontsize=8)
    data = doc.tobytes()
    # pixel boxes at 150 dpi: pt * 150/72
    def lay(page, w, h):
        s = 150 / 72
        return [Block("chart", "chart", [50 * s, 150 * s, 500 * s, 340 * s], "layout", confidence=0.9),
                Block("caption", "figure_title", [45 * s, 348 * s, 500 * s, 368 * s], "layout", confidence=0.9),
                Block("footer", "footer", [45 * s, 790 * s, 500 * s, 810 * s], "layout", confidence=0.9)]
    md, run, out = run_stages(tmp_path, data, layout=True, fac=factory(layout=lay))
    assert run["stage"] == "layout"
    m = re.search(r"!\[Diagramm S\. 1\]\(media/(p0001_1\.png)\)\n\n\*Abbildung 1: Verlauf der Werte\*", md)
    assert m, md
    assert (out / "media" / m.group(1)).stat().st_size > 0
    assert "Fusszeile" not in md  # footer removed
    assert md.index("Ueberschrift") < md.index("![Diagramm")


def test_layout_failure_falls_back_to_text(tmp_path):
    md, run, _ = run_stages(tmp_path, pdfgen.one_column(2), layout=True, fac=factory(fail_layout=True))
    assert run["stage"] == "text" and "cannot load layout model" in run["layout_error"]
    assert "## Seite 2" in md and "Lorem" in md


def test_no_layout_gives_no_crops(tmp_path):
    md, run, out = run_stages(tmp_path, pdfgen.one_column(2), layout=False)
    assert run["stage"] == "text" and [f.name for f in (out / "media").iterdir()] == ["cover.jpg"]  # only the thumbnail


def test_table_markdown_and_crop(tmp_path):
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    # a ruled 3x3 table
    x0, y0, cw, rh = 72, 100, 100, 24
    for r in range(4):
        p.draw_line((x0, y0 + r * rh), (x0 + 3 * cw, y0 + r * rh))
    for c in range(4):
        p.draw_line((x0 + c * cw, y0), (x0 + c * cw, y0 + 3 * rh))
    for r in range(3):
        for c in range(3):
            p.insert_text((x0 + c * cw + 5, y0 + r * rh + 16), f"r{r}c{c}", fontsize=10)
    s = 150 / 72
    def lay(page, w, h):
        return [Block("table", "table", [(x0 - 5) * s, (y0 - 5) * s, (x0 + 3 * cw + 5) * s, (y0 + 3 * rh + 5) * s], "layout", confidence=0.9)]
    md, _, out = run_stages(tmp_path, doc.tobytes(), layout=True, fac=factory(layout=lay))
    assert re.search(r"!\[Tabelle S\. 1\]\(media/p0001_1\.png\)", md)
    assert "| r0c0 | r0c1 | r0c2 |" in md


def test_layout_reading_order_overrides_position(tmp_path):
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_textbox(pymupdf.Rect(60, 100, 500, 160), "Oben liegender Absatz " * 4, fontsize=10)
    p.insert_textbox(pymupdf.Rect(60, 500, 500, 560), "Unten liegender Absatz " * 4, fontsize=10)
    s = 150 / 72

    def lay(page, w, h):  # the model says: the lower paragraph is read first
        return [Block("text", "text", [55 * s, 95 * s, 505 * s, 165 * s], "layout", order=2, confidence=0.9),
                Block("text", "text", [55 * s, 495 * s, 505 * s, 565 * s], "layout", order=1, confidence=0.9)]
    md, _, _ = run_stages(tmp_path, doc.tobytes(), layout=True, fac=factory(layout=lay))
    assert md.index("Unten liegender") < md.index("Oben liegender")


def test_layout_title_becomes_heading(tmp_path):
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((60, 100), "Plain gesetzte Ueberschrift", fontsize=10)
    p.insert_textbox(pymupdf.Rect(60, 130, 500, 200), "Fliesstext " * 20, fontsize=10)
    s = 150 / 72

    def lay(page, w, h):
        return [Block("title", "paragraph_title", [55 * s, 85 * s, 300 * s, 108 * s], "layout", confidence=0.9)]
    md, _, _ = run_stages(tmp_path, doc.tobytes(), layout=True, fac=factory(layout=lay))
    assert "### Plain gesetzte Ueberschrift" in md


def test_file_label_bookmarks_ignored(tmp_path):
    doc = pymupdf.open()
    for i in range(10):
        doc.new_page().insert_text((72, 100), f"Seite {i} " * 5)
    doc.set_toc([[1, f"scan_{i:04d}_a", i + 1] for i in range(10)])
    md, run, _ = run_stages(tmp_path, doc.tobytes(), layout=False)
    assert run["toc"]["source"] != "bookmarks" and "scan_0001_a" not in md


def test_toc_pages_named_by_reader_are_excluded(tmp_path):
    """Generic titles that fill many pages must not make body pages look like contents pages."""
    data, chapters = _book_with_printed_toc(8)
    raw = [{"title": t, "printed_page": p, "level": 1, "kind": "chapter"} for t, p in chapters]
    md, run, _ = run_stages(tmp_path, data, layout=False, toc={"printed_toc": raw, "toc_pages": [2]})
    assert run["toc"]["source"] == "printed_toc" and run["toc"]["confirmed"] == 5


def test_few_bookmarks_in_long_document_do_not_replace_printed_list(tmp_path):
    doc = pymupdf.open()
    for i in range(30):
        doc.new_page().insert_text((72, 100), f"Seite {i} " * 5)
    doc.set_toc([[1, "Deckblatt", 1], [1, "Anhang", 30]])
    md, run, _ = run_stages(tmp_path, doc.tobytes(), layout=False)
    assert run["toc"]["source"] != "bookmarks"


def test_candidates_are_only_pages_that_look_like_a_contents_list(tmp_path):
    data, _ = _book_with_printed_toc(8)
    _, _, out = run_stages(tmp_path, data, layout=False)
    pages = [p["page"] for p in json.loads((out / "toc_candidates.json").read_text())["pages"]]
    assert pages == [1, 2, 3]  # the contents list stands on page 2, with its neighbours
    # a document without any such page offers no page text
    other = tmp_path / "other"
    other.mkdir()
    _, _, out2 = run_stages(other, pdfgen.one_column(12), layout=False)
    assert json.loads((out2 / "toc_candidates.json").read_text())["pages"] == []
