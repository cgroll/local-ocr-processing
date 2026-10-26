from pathlib import Path

import pytest
from PIL import Image

from docparse.enrich import blocks as B
from docparse.enrich import runner as R
from docparse.enrich.format import PageEnrichment, VisualBlock, read_result, result_path, write_result
from docparse.parse.format import Block, PageResult, write_result as write_engine_result
from docparse.parse.select import DocPages

DOC = "ds-example"


def _write_engine(root: Path, engine: str, page: int, blocks: list[Block], status: str = "ok") -> None:
    write_engine_result(PageResult(DOC, page, 150, 1275, 1650, engine, status=status, blocks=blocks), root)


def _text_block(order: int, text: str, type_: str = "text") -> Block:
    return Block(type=type_, label=type_, bbox=[10.0, 10.0 + order * 20, 200.0, 25.0 + order * 20], engine="pymupdf", order=order, text=text)


# --- choose_text_source ---------------------------------------------------

def test_choose_text_source_prefers_pymupdf_when_it_has_text(tmp_path):
    _write_engine(tmp_path, "pymupdf", 1, [_text_block(0, "hello")])
    source, result = B.choose_text_source(DOC, 1, tmp_path)
    assert source == "pymupdf" and result.blocks[0].text == "hello"


def test_choose_text_source_falls_back_to_ocr_on_pure_scan(tmp_path):
    _write_engine(tmp_path, "pymupdf", 1, [Block(type="image", label="image", bbox=[0, 0, 10, 10], engine="pymupdf")])
    _write_engine(tmp_path, "ocr", 1, [Block(type="line", label="text_line", bbox=[0, 0, 10, 10], engine="ocr", order=0, text="scanned text")])
    source, result = B.choose_text_source(DOC, 1, tmp_path)
    assert source == "ocr" and result.blocks[0].text == "scanned text"


def test_choose_text_source_none_when_nothing_available(tmp_path):
    source, result = B.choose_text_source(DOC, 1, tmp_path)
    assert source == "none" and result is None


# --- narrative_text --------------------------------------------------------

def test_narrative_text_is_ordered_and_skips_visual_blocks(tmp_path):
    source = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=[
        _text_block(1, "second"), _text_block(0, "first"),
        Block(type="table", label="table", bbox=[0, 0, 10, 10], engine="pymupdf", order=2, html="<table></table>"),
    ])
    assert B.narrative_text(source) == "first\n\nsecond"


# --- visual_candidates / decorative filter ---------------------------------

# Real PP-DocLayoutV3 boxes from ds-tps62130 p1 (see experiments/multimodal-repr-test/): four
# small TI marketing icons (5000-7350 px^2) plus a genuine table, chart and schematic figure
# (30000+ px^2). The filter must drop the icons and keep the real content.
ICONS = [
    Block(type="figure", label="header_image", bbox=[321.0, 13.0, 449.0, 54.0], engine="layout"),
    Block(type="figure", label="header_image", bbox=[475.0, 13.0, 642.0, 57.0], engine="layout"),
    Block(type="figure", label="header_image", bbox=[665.0, 14.0, 807.0, 54.0], engine="layout"),
    Block(type="figure", label="header_image", bbox=[833.0, 13.0, 955.0, 54.0], engine="layout"),
]
REAL_CONTENT = [
    Block(type="table", label="table", bbox=[654.0, 1063.0, 1156.0, 1123.0], engine="layout"),
    Block(type="chart", label="chart", bbox=[691.0, 1187.0, 1114.0, 1473.0], engine="layout"),
    Block(type="figure", label="image", bbox=[104.0, 1190.0, 648.0, 1346.0], engine="layout"),
]


def test_decorative_icons_are_filtered_but_real_content_is_kept():
    layout = PageResult(DOC, 1, 150, 1275, 1650, "layout", blocks=ICONS + REAL_CONTENT)
    kept = B.visual_candidates(layout)
    assert len(kept) == 3
    assert {c.label for c in kept} == {"table", "chart", "image"}


def test_visual_candidates_are_sorted_top_to_bottom():
    layout = PageResult(DOC, 1, 150, 1275, 1650, "layout", blocks=list(reversed(REAL_CONTENT)))
    kept = B.visual_candidates(layout)
    assert [c.bbox[1] for c in kept] == sorted(c.bbox[1] for c in REAL_CONTENT)


# --- crop_region -------------------------------------------------------------

def test_crop_region_matches_bbox_pixel_size(tmp_path):
    png = tmp_path / "page.png"
    Image.new("RGB", (300, 400), "white").save(png)
    crop = B.crop_region(png, [10.4, 20.6, 110.4, 70.6])
    assert crop.size == (100, 50)


# --- table_content -----------------------------------------------------------

def test_table_content_prefers_vl_html_over_pymupdf():
    pymupdf_result = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=[
        Block(type="table", label="table", bbox=[0, 0, 10, 10], engine="pymupdf", html="<table><tr><td>pymupdf</td></tr></table>"),
    ])
    vl_result = PageResult(DOC, 1, 150, 1275, 1650, "vl", blocks=[
        Block(type="table", label="table", bbox=[0, 0, 10, 10], engine="vl", html="<table><tr><td>vl</td></tr></table>"),
    ])
    content, source = B.table_content(0, pymupdf_result, vl_result)
    assert source == "vl" and "vl" in content


def test_table_content_falls_back_to_pymupdf_without_vl():
    pymupdf_result = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=[
        Block(type="table", label="table", bbox=[0, 0, 10, 10], engine="pymupdf", html="<table><tr><td>pymupdf</td></tr></table>"),
    ])
    content, source = B.table_content(0, pymupdf_result, None)
    assert source == "pymupdf" and "pymupdf" in content


def test_table_content_none_when_rank_out_of_range():
    pymupdf_result = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=[])
    assert B.table_content(0, pymupdf_result, None) == (None, None)


# --- format round-trip --------------------------------------------------------

def test_enrich_format_round_trip(tmp_path):
    result = PageEnrichment(
        DOC, 1, "pymupdf", narrative_text="hello",
        visual_blocks=[VisualBlock(type="table", label="table", bbox=[0, 0, 10, 10], position=0,
                                    crop_path="x.png", description="a table", content_text="<table></table>", content_source="vl")],
    )
    path = write_result(result, tmp_path)
    assert path == result_path(DOC, 1, tmp_path)
    loaded = read_result(path)
    assert loaded == result


# --- runner --------------------------------------------------------------------

def _doc_pages(tmp_path, pages=(1,)):
    return DocPages(DOC, tmp_path / "document.pdf", list(pages))


def test_enrich_page_without_manager_skips_description(tmp_path):
    _write_engine(tmp_path, "pymupdf", 1, [_text_block(0, "hello")])
    _write_engine(tmp_path, "layout", 1, REAL_CONTENT)
    pages_dir = tmp_path / "pages" / DOC
    pages_dir.mkdir(parents=True)
    Image.new("RGB", (1275, 1650), "white").save(pages_dir / "0001.png")

    result, block_errors = R.enrich_page(_doc_pages(tmp_path), 1, None, tmp_path, tmp_path / "pages")
    assert result.status == "ok" and block_errors == 0
    assert len(result.visual_blocks) == 3
    assert all(vb.description is None for vb in result.visual_blocks)
    assert Path(result.visual_blocks[0].crop_path).exists()


def test_enrich_page_is_an_error_without_a_text_source(tmp_path):
    result, block_errors = R.enrich_page(_doc_pages(tmp_path), 1, None, tmp_path, tmp_path / "pages")
    assert result.status == "error" and "text source" in result.error and block_errors == 0


def test_enrich_page_block_failure_does_not_fail_the_page(tmp_path, monkeypatch):
    _write_engine(tmp_path, "pymupdf", 1, [_text_block(0, "hello")])
    _write_engine(tmp_path, "layout", 1, REAL_CONTENT)
    pages_dir = tmp_path / "pages" / DOC
    pages_dir.mkdir(parents=True)
    Image.new("RGB", (1275, 1650), "white").save(pages_dir / "0001.png")

    def boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(B, "crop_region", boom)
    result, block_errors = R.enrich_page(_doc_pages(tmp_path), 1, None, tmp_path, tmp_path / "pages")
    assert result.status == "ok" and block_errors == 3
    assert all(vb.status == "error" and "boom" in vb.error for vb in result.visual_blocks)


def test_run_skips_done_pages_and_force_recomputes(tmp_path):
    _write_engine(tmp_path, "pymupdf", 1, [_text_block(0, "hello")])
    pages_dir = tmp_path / "pages" / DOC
    pages_dir.mkdir(parents=True)
    Image.new("RGB", (1275, 1650), "white").save(pages_dir / "0001.png")
    docs = [_doc_pages(tmp_path)]

    counts = R.run(docs, None, results_dir=tmp_path, pages_dir=tmp_path / "pages", log=lambda *a: None)
    assert counts.done == 1 and counts.skipped == 0

    counts = R.run(docs, None, results_dir=tmp_path, pages_dir=tmp_path / "pages", log=lambda *a: None)
    assert counts.done == 0 and counts.skipped == 1

    counts = R.run(docs, None, force=True, results_dir=tmp_path, pages_dir=tmp_path / "pages", log=lambda *a: None)
    assert counts.done == 1 and counts.skipped == 0
