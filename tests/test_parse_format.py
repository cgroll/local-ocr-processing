import numpy as np
import pymupdf
import pytest

from docparse.parse.format import (
    Block, PageResult, read_result, validate_result, validate_tree, write_result,
)
from docparse.parse.render import rect_to_pixels, render_page


def sample_result(**kw) -> PageResult:
    block = Block(type="text", label="paragraph", bbox=[10, 20, 100, 60], engine="ocr", confidence=0.9, text="hi")
    return PageResult("doc1", 3, 150, 1275, 1650, "ocr", "3.7.0", seconds=1.2, blocks=[block], **kw)


def test_round_trip(tmp_path):
    result = sample_result()
    path = write_result(result, tmp_path)
    assert path == tmp_path / "ocr" / "doc1" / "0003.json"
    assert read_result(path) == result
    assert not list(tmp_path.rglob("*.tmp"))


def test_valid_result_has_no_errors():
    assert validate_result(sample_result()) == []


def test_box_outside_image():
    r = sample_result()
    r.blocks[0].bbox = [10, 20, 2000, 60]
    assert any("outside image" in e for e in validate_result(r))


def test_malformed_box_and_unknown_type():
    r = sample_result()
    r.blocks[0].bbox = [50, 20, 10, 60]
    r.blocks[0].type = "banana"
    errors = validate_result(r)
    assert any("malformed bbox" in e for e in errors) and any("unknown type" in e for e in errors)


def test_error_result_needs_message():
    r = PageResult("d", 1, 150, 100, 100, "vl", status="error")
    assert any("without message" in e for e in validate_result(r))


def test_validate_tree_reports_file(tmp_path):
    good = sample_result()
    bad = sample_result()
    bad.page = 4
    bad.blocks[0].bbox = [0, 0, 5000, 5000]
    write_result(good, tmp_path)
    write_result(bad, tmp_path)
    count, errors = validate_tree(tmp_path)
    assert count == 2 and len(errors) == 1 and "0004.json" in errors[0]


def make_pdf(path, rotation=0):
    with pymupdf.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.draw_rect(pymupdf.Rect(30, 20, 130, 60), fill=(0, 0, 0))
        page.set_rotation(rotation)
        doc.save(path)


def test_render_size_matches_points_times_dpi(tmp_path):
    pdf = tmp_path / "a.pdf"
    make_pdf(pdf)
    out = tmp_path / "pages" / "d" / "0001.png"
    rp = render_page(pdf, 1, dpi=144, out_path=out)
    assert (rp.width, rp.height) == (600, 400) and out.exists()
    assert rp.image.shape == (400, 600, 3)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rect_lands_on_dark_pixels_for_any_rotation(tmp_path, rotation):
    pdf = tmp_path / "r.pdf"
    make_pdf(pdf, rotation)
    rp = render_page(pdf, 1, dpi=100)
    x0, y0, x1, y1 = (round(v) for v in rect_to_pixels((30, 20, 130, 60), rp.to_pixels))
    gray = rp.image.mean(axis=2)
    inside = gray[y0 + 2:y1 - 2, x0 + 2:x1 - 2]
    assert inside.max() < 10  # the box is black
    assert (gray < 10).sum() <= (x1 - x0) * (y1 - y0) * 1.05  # nothing dark outside the mapped box
