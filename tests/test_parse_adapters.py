import json
from pathlib import Path

import pymupdf
import pytest

from docparse.parse.adapters import layout, ocr, pymupdf as pm_adapter, vl
from docparse.parse.format import BLOCK_TYPES, PageResult, validate_result
from docparse.parse.labels import LAYOUT_LABELS, block_type
from docparse.parse.render import render_page

FIX = Path(__file__).parent / "fixtures"
W, H = 1275, 1650


def load(name):
    return json.loads((FIX / name).read_text())


def check_valid(engine, blocks):
    result = PageResult("d", 1, 150, W, H, engine, blocks=blocks)
    assert validate_result(result) == []


def test_labels_map_to_known_types():
    assert set(LAYOUT_LABELS.values()) <= set(BLOCK_TYPES)
    assert block_type("table") == "table" and block_type("header") == "header"
    assert block_type("something_new") == "other"


def test_layout_adapter():
    blocks = layout.to_blocks(load("layout_raw.json"))
    assert len(blocks) == 10
    assert [b.type for b in blocks[:4]] == ["figure", "header", "header", "title"]
    assert blocks[3].label == "paragraph_title" and blocks[3].order == 1
    assert blocks[0].order is None and 0 < blocks[3].confidence <= 1 and blocks[3].text is None
    assert len(blocks[3].polygon) == 4
    check_valid("layout", blocks)


def test_ocr_adapter():
    raw = load("ocr_raw.json")
    blocks = ocr.to_blocks(raw)
    assert len(blocks) == len(raw["rec_texts"]) == 75
    b = blocks[0]
    assert b.type == "line" and b.text == raw["rec_texts"][0] and b.confidence == pytest.approx(raw["rec_scores"][0])
    assert b.bbox == [float(v) for v in raw["rec_boxes"][0]] and len(b.polygon) == 4
    check_valid("ocr", blocks)


def test_ocr_empty_page():
    assert ocr.to_blocks({"rec_texts": [], "rec_scores": [], "rec_polys": [], "rec_boxes": []}) == []


def test_vl_adapter_keeps_header_and_footer():
    raw = load("vl_raw.json")
    blocks = vl.to_blocks(raw["blocks"])
    assert [b.type for b in blocks].count("header") == 2 and "footer" in [b.type for b in blocks]
    assert blocks[1].text == "LM317" and blocks[1].markdown == "LM317" and blocks[1].confidence is None
    assert blocks[0].text is None  # image blocks have no content
    assert [b.order for b in blocks] == list(range(len(blocks)))
    check_valid("vl", blocks)


def test_vl_table_goes_to_html():
    blocks = vl.to_blocks(load("vl_table_raw.json")["blocks"])
    (table,) = [b for b in blocks if b.type == "table"]
    assert table.html.startswith("<table>") and table.markdown is None and table.text is None
    assert "DEVICE PINOUT" in table.html


def make_pdf(path):
    with pymupdf.open() as doc:
        page = doc.new_page(width=300, height=400)
        page.insert_text((40, 60), "Hello adapter", fontsize=14)
        # a 3x3 table with ruled cells (smaller grids are not detected by PyMuPDF)
        for i in range(3):
            for j in range(3):
                page.draw_rect(pymupdf.Rect(40 + i * 60, 150 + j * 30, 100 + i * 60, 180 + j * 30), width=1)
                page.insert_text((46 + i * 60, 170 + j * 30), f"c{i}{j}", fontsize=10)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
        pix.set_rect(pix.irect, (200, 30, 30))
        page.insert_image(pymupdf.Rect(220, 40, 280, 100), pixmap=pix)
        page.draw_circle((100, 320), 30, color=(0, 0, 1), fill=(0.8, 0.8, 1))
        doc.save(path)


@pytest.fixture
def native_page(tmp_path):
    pdf = tmp_path / "n.pdf"
    make_pdf(pdf)
    rp = render_page(pdf, 1, 144)  # 2 px per point
    return pdf, rp


def test_pymupdf_adapter_native(native_page):
    pdf, rp = native_page
    with pymupdf.open(pdf) as doc:
        blocks = pm_adapter.to_blocks(doc[0], rp.to_pixels)
    by_type = {}
    for b in blocks:
        by_type.setdefault(b.type, []).append(b)
    assert all(b.confidence is None and b.engine == "pymupdf" for b in blocks)
    text = by_type["text"][0]
    assert "Hello adapter" in text.text and text.bbox[0] == pytest.approx(80, abs=4)  # 40 pt * 2
    (table,) = by_type["table"]
    assert "<td>c00</td>" in table.html and "<td>c22</td>" in table.html and table.html.count("<tr>") == 3
    x0, y0, x1, y1 = table.bbox
    assert 80 <= x0 < x1 <= 440 and 300 <= y0 < y1 <= 480  # inside the ruled grid (2 px per point)
    assert not any("c11" in t.text for t in by_type.get("text", []))  # table cells are not repeated as text
    (img,) = by_type["image"]
    assert img.bbox == pytest.approx([440, 80, 560, 200], abs=2)
    assert any(abs((d.bbox[0] + d.bbox[2]) / 2 - 200) < 6 for d in by_type["drawing"])  # the circle
    result = PageResult("d", 1, 144, rp.width, rp.height, "pymupdf", blocks=blocks)
    assert validate_result(result) == []


def test_pymupdf_scanned_page_has_only_an_image(tmp_path):
    with pymupdf.open() as doc:
        page = doc.new_page(width=200, height=200)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
        pix.set_rect(pix.irect, (240, 240, 240))
        page.insert_image(page.rect, pixmap=pix)
        doc.save(tmp_path / "s.pdf")
    rp = render_page(tmp_path / "s.pdf", 1, 72)
    with pymupdf.open(tmp_path / "s.pdf") as doc:
        blocks = pm_adapter.to_blocks(doc[0], rp.to_pixels)
    assert [b.type for b in blocks] == ["image"]
