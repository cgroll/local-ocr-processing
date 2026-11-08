import json
import re

import pytest

from docparse.pdf_ingest import __main__ as cli
from docparse.pdf_ingest import pipeline as P

import pdfgen


def run(tmp_path, data: bytes, *flags: str):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(data)
    out = tmp_path / "out"
    code = cli.main(["--pdf", str(pdf), "--out", str(out), "--no-layout", "--ocr", "off", *flags])
    assert code == 0
    return (out / "document.md").read_text(encoding="utf-8"), json.loads((out / "run.json").read_text()), out


def test_cli_small_pdf_without_gpu(tmp_path):
    md, run_json, out = run(tmp_path, pdfgen.one_column(2))
    assert (out / "run.json").exists() and run_json["pages"] == 2 and run_json["stage"] == "text"
    assert "## Seite 1" in md and "## Seite 2" in md


def test_page_markers_complete_one_line_each(tmp_path):
    md, _, _ = run(tmp_path, pdfgen.one_column(4))
    markers = re.findall(r"(?m)^## Seite (\d+)\b.*$", md)
    assert markers == ["1", "2", "3", "4"]
    assert len(re.findall(r"(?m)^## Seite 3\b", md)) == 1


def test_empty_page_has_marker_and_hint(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()
    p = doc.new_page()
    p.insert_text((72, 100), "Text auf Seite zwei " * 3)
    md, _, _ = run(tmp_path, doc.tobytes())
    assert re.search(r"## Seite 1\n\n\*\(kein Text erkannt\)\*", md)
    assert "## Seite 2" in md


def test_headings_from_font_size_and_paragraph_lines(tmp_path):
    md, _, _ = run(tmp_path, pdfgen.one_column(2))
    assert "### Kapitel 1 Titel" in md
    # a paragraph is one line, not one line per PDF line
    para = next(l for l in md.splitlines() if l.startswith("Absatz 1.1:"))
    assert "labore et dolore" in para and "Lorem ipsum" in para


def test_two_columns_left_before_right(tmp_path):
    md, _, _ = run(tmp_path, pdfgen.two_columns(1))
    left = max(md.index(f"L{k} seite1") for k in range(1, 6))
    right = min(md.index(f"R{k} seite1") for k in range(1, 6))
    assert left < right


def test_hyphenation_resolved_and_sentence_in_one_line(tmp_path):
    md, _, _ = run(tmp_path, pdfgen.hyphenated())
    assert "Silbentrennung am Zeilenende" in md


def test_running_footer_removed_page_numbers_marked(tmp_path):
    md, run_json, _ = run(tmp_path, pdfgen.one_column(5))
    assert "Laufender Fusszeilentext" not in md
    # printed number equals the PDF page: no extra marker text
    assert "gedruckt" not in md


def test_printed_page_marker_when_offset(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    for i in range(6):
        p = doc.new_page()
        p.insert_text((72, 100), f"Inhalt der Seite {i} " * 3)
        p.insert_text((300, 820), str(i + 6), fontsize=8)
    md, run_json, _ = run(tmp_path, doc.tobytes())
    assert "## Seite 1 · gedruckt S. 6" in md
    assert run_json["printed_pages"]["1"] == 6


def test_embedded_image_between_paragraphs(tmp_path):
    md, _, out = run(tmp_path, pdfgen.with_image())
    before, after = md.index("Absatz vor dem Bild"), md.index("Absatz nach dem Bild")
    img = re.search(r"!\[Bild S\. 1\]\(media/(p0001_\d+\.png)\)", md)
    assert img and before < img.start() < after
    assert (out / "media" / img.group(1)).stat().st_size > 0


def test_tiny_image_skipped(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 100), "Text " * 10)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False)
    pix.clear_with(0)
    p.insert_image(pymupdf.Rect(72, 150, 92, 170), pixmap=pix)
    md, _, out = run(tmp_path, doc.tobytes())
    assert "media/" not in md


def test_encrypted_pdf_rejected(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "geheim")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(data)
    assert cli.main(["--pdf", str(pdf), "--out", str(tmp_path / "o")]) == P.EXIT_INPUT


def test_not_a_pdf_rejected(tmp_path):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"<html>nope</html>")
    assert cli.main(["--pdf", str(pdf), "--out", str(tmp_path / "o")]) == P.EXIT_INPUT


def test_too_many_pages_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "MAX_PAGES", 2)
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(pdfgen.one_column(3))
    assert cli.main(["--pdf", str(pdf), "--out", str(tmp_path / "o")]) == P.EXIT_INPUT


def test_title_and_author_from_metadata(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Hallo Welt " * 5)
    doc.set_metadata({"title": "Ein Titel", "author": "A. Autorin", "creationDate": "D:20230115120000Z"})
    _, run_json, _ = run(tmp_path, doc.tobytes())
    assert (run_json["title"], run_json["author"], run_json["created"]) == ("Ein Titel", "A. Autorin", "2023-01-15")


def test_title_from_first_heading_when_metadata_is_filename(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 90), "Meine Ueberschrift", fontsize=22, fontname="hebo")
    p.insert_textbox(pymupdf.Rect(72, 110, 520, 300), "Fliesstext " * 60, fontsize=10)
    doc.set_metadata({"title": "report_final.pdf"})
    _, run_json, _ = run(tmp_path, doc.tobytes())
    assert run_json["title"] == "Meine Ueberschrift"


def test_ocr_text_layer_with_big_fonts_gives_no_headings(tmp_path):
    """A scanned book with an OCR text layer: every line is its own block with an odd size."""
    import pymupdf
    doc = pymupdf.open()
    p = doc.new_page()
    for i in range(14):
        p.insert_text((72, 60 + i * 40), f"Zeile {i} des Fliesstextes ohne eigene Bedeutung", fontsize=9 + (i % 2) * 5)
    md, _, _ = run(tmp_path, doc.tobytes())
    assert "###" not in md and "Zeile 13" in md


def test_cover_thumbnail_of_first_page(tmp_path):
    from PIL import Image
    _, run_json, out = run(tmp_path, pdfgen.one_column(2))
    cover = out / "media" / "cover.jpg"
    assert run_json["cover"] is True and cover.stat().st_size > 0
    with Image.open(cover) as im:
        assert im.width == 600 and im.height > im.width  # portrait page
