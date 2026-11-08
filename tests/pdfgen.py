"""Small synthetic PDFs for the pdf_ingest tests (no real content)."""
import pymupdf

LOREM = ("Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut "
         "labore et dolore magna aliqua ")


def _para(doc_page: pymupdf.Page, rect: pymupdf.Rect, text: str, size: float = 10, font: str = "helv") -> None:
    assert doc_page.insert_textbox(rect, text, fontsize=size, fontname=font) >= 0, "test text does not fit its box"


def one_column(pages: int = 3, headings: bool = True) -> bytes:
    """Pages with a heading, paragraphs and a repeating footer with a page number."""
    doc = pymupdf.open()
    for i in range(pages):
        p = doc.new_page()
        y = 72
        if headings:
            p.insert_text((72, y), f"Kapitel {i + 1} Titel", fontsize=20, fontname="hebo")
            y += 30
        for k in range(3):
            _para(p, pymupdf.Rect(72, y, 520, y + 70), f"Absatz {i + 1}.{k + 1}: " + LOREM * 2)
            y += 80
        p.insert_text((72, 800), "Laufender Fusszeilentext", fontsize=8)
        p.insert_text((300, 820), str(i + 1), fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data


def two_columns(pages: int = 2) -> bytes:
    """Left column paragraphs L1..L5, right column R1..R5 per page."""
    doc = pymupdf.open()
    for i in range(pages):
        p = doc.new_page()
        for col, (x0, tag) in enumerate(((60, "L"), (320, "R"))):
            y = 80
            for k in range(5):
                _para(p, pymupdf.Rect(x0, y, x0 + 230, y + 120), f"{tag}{k + 1} seite{i + 1} " + LOREM * 2)
                y += 130
    data = doc.tobytes()
    doc.close()
    return data


def hyphenated() -> bytes:
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 100), "Das ist ein Satz mit Silben-", fontsize=11)
    p.insert_text((72, 114), "trennung am Zeilenende und ein Test.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def with_bookmarks(pages: int = 12) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        p = doc.new_page()
        p.insert_text((72, 100), f"Abschnitt {i + 1} Ueberschrift", fontsize=18, fontname="hebo")
        _para(p, pymupdf.Rect(72, 130, 520, 260), LOREM * 3)
    doc.set_toc([[1, "Einleitung", 1], [2, "Hintergrund", 2], [1, "Methoden", min(5, pages)], [1, "Ergebnisse", min(9, pages)], [1, "Anhang", pages]])
    data = doc.tobytes()
    doc.close()
    return data


def scan_page_mixed() -> bytes:
    """Page 1 text, page 2 only an image (a scan), page 3 text."""
    doc = pymupdf.open()
    for i in range(3):
        p = doc.new_page()
        if i == 1:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 80), False)
            pix.clear_with(230)
            p.insert_image(p.rect, pixmap=pix, keep_proportion=False)
        else:
            _para(p, pymupdf.Rect(72, 80, 520, 300), LOREM * 3)
    data = doc.tobytes()
    doc.close()
    return data


def with_image() -> bytes:
    doc = pymupdf.open()
    p = doc.new_page()
    _para(p, pymupdf.Rect(72, 60, 520, 120), "Absatz vor dem Bild. " + LOREM)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 90), False)
    pix.clear_with(120)
    p.insert_image(pymupdf.Rect(72, 150, 272, 300), pixmap=pix)
    _para(p, pymupdf.Rect(72, 330, 520, 400), "Absatz nach dem Bild. " + LOREM)
    data = doc.tobytes()
    doc.close()
    return data
