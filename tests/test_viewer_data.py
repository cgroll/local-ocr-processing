import json

from docparse.dataset.manifest import Entry
from docparse.enrich.format import PageEnrichment, VisualBlock, write_result as write_enrichment
from docparse.parse.format import Block, PageResult, result_path, write_result
from docparse.viewer.data import ENGINES, embed_json, index_data, markdown_html, page_data, page_numbers, _visual_blocks_payload


def doc(id="d1", **kw):
    return Entry(id=id, group="datasheet", tags="table", title="Doc " + id, kind="native", pages="10", page_range="1-4", **kw)


def put(root, engine, doc_id, page, status="ok", blocks=(), error=None):
    write_result(PageResult(doc_id, page, 150, 100, 200, engine, status=status, error=error, blocks=list(blocks)), root)


def blk(engine, **kw):
    return Block(**{"type": "text", "label": "text", "bbox": [1, 2, 30, 40], "engine": engine, **kw})


def test_page_numbers():
    assert page_numbers(doc()) == [1, 2, 3, 4]
    assert page_numbers(Entry(id="x", pages="3")) == [1, 2, 3]


def test_missing_engine_and_error_result_marked(tmp_path):
    put(tmp_path, "pymupdf", "d1", 1, blocks=[blk("pymupdf", text="hi")])
    put(tmp_path, "ocr", "d1", 1, status="error", error="boom")
    data = page_data(doc(), 1, tmp_path)
    assert data["engines"]["pymupdf"]["state"] == "ok"
    assert data["engines"]["ocr"] == {"state": "error", "error": "boom"}
    assert data["engines"]["vl"] == {"state": "missing"}
    assert data["engines"]["layout"] == {"state": "missing"}
    assert data["size"] == [100, 200]
    assert data["engines"]["pymupdf"]["blocks"][0]["id"] == "pymupdf:0"


def test_unreadable_result_is_error(tmp_path):
    p = result_path("vl", "d1", 1, tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("{not json")
    assert page_data(doc(), 1, tmp_path)["engines"]["vl"]["state"] == "error"


def test_table_html_sanitized(tmp_path):
    put(tmp_path, "vl", "d1", 1, blocks=[blk("vl", type="table", html='<table><tr><td onclick="x()">a<script>1</script></td></tr></table>')])
    html = page_data(doc(), 1, tmp_path)["engines"]["vl"]["blocks"][0]["html"]
    assert html == "<table><tr><td>a</td></tr></table>"


def test_script_end_in_text_cannot_close_block(tmp_path):
    text = "</script><script>alert(1)</script><!-- x"
    put(tmp_path, "pymupdf", "d1", 1, blocks=[blk("pymupdf", text=text)])
    data = page_data(doc(), 1, tmp_path)
    embedded = embed_json(data)
    assert "</" not in embedded and "<script" not in embedded and "<!--" not in embedded
    assert json.loads(embedded)["engines"]["pymupdf"]["blocks"][0]["text"] == text


# --- markdown_html: Markdown representation (viewer-markdown-view) -----------------

def test_page_data_includes_markdown_html(tmp_path):
    put(tmp_path, "pymupdf", "d1", 1, blocks=[blk("pymupdf", type="title", text="My Title", order=0)])
    write_enrichment(PageEnrichment("d1", 1, "pymupdf", visual_blocks=[
        VisualBlock(type="table", label="table", bbox=[0, 0, 10, 10], position=0,
                    crop_path="x.png", content_text="<table><tr><td>v</td></tr></table>", content_source="pymupdf"),
    ]), tmp_path)
    data = page_data(doc(), 1, tmp_path)
    assert "markdown_html" in data
    assert "<h3>My Title</h3>" in data["markdown_html"]
    assert "<table>" in data["markdown_html"]


def test_markdown_html_escapes_and_drops_disallowed_content(tmp_path):
    put(tmp_path, "pymupdf", "d1", 1, blocks=[blk("pymupdf", type="text", text="<script>alert(1)</script>ok", order=0)])
    write_enrichment(PageEnrichment("d1", 1, "pymupdf"), tmp_path)
    html = markdown_html("d1", 1, tmp_path)
    assert "<script>" not in html
    assert "ok" in html


def test_markdown_html_missing_enrichment_shows_note_not_error(tmp_path):
    html = markdown_html("d1", 1, tmp_path)
    assert "Keine Anreicherung" in html


def test_markdown_html_no_text_source_shows_note(tmp_path):
    # Enrichment exists, but neither pymupdf nor ocr produced anything and there are no visual
    # blocks -- choose_text_source returns ("none", None) and render_page has nothing to add
    # beyond the page heading.
    write_enrichment(PageEnrichment("d1", 1, "none"), tmp_path)
    html = markdown_html("d1", 1, tmp_path)
    assert "Keine Textquelle" in html


# --- visual_blocks: image gallery payload for the Markdown tab (viewer-markdown-figures) -----

def test_page_data_includes_visual_blocks_table_and_figure(tmp_path):
    # pymupdf/ocr text blocks become the "found texts" fragment pool (geometry overlap).
    put(tmp_path, "pymupdf", "d1", 1, blocks=[
        blk("pymupdf", type="title", bbox=[100, 100, 180, 120], text="T", order=0),  # far from both blocks
        blk("pymupdf", type="text", bbox=[1, 1, 9, 9], text="inside table", order=1),  # overlaps the table
    ])
    put(tmp_path, "ocr", "d1", 1, blocks=[
        blk("ocr", type="line", bbox=[22, 22, 38, 58], text="inside figure", order=0),  # overlaps the figure
    ])
    write_enrichment(PageEnrichment("d1", 1, "pymupdf", visual_blocks=[
        VisualBlock(type="table", label="table", bbox=[0, 0, 10, 10], position=0,
                    crop_path="x.png", content_text="<table><tr><td>v</td></tr></table>", content_source="vl"),
        VisualBlock(type="figure", label="image", bbox=[20, 20, 40, 60], position=1,
                    crop_path="y.png", description="A schematic diagram."),
    ]), tmp_path)
    data = page_data(doc(), 1, tmp_path)
    assert data["visual_blocks"] == [
        {"type": "table", "label": "table", "bbox": [0, 0, 10, 10], "description": None, "status": "ok",
         "fragments": ["inside table"], "html": "<table><tr><td>v</td></tr></table>"},
        {"type": "figure", "label": "image", "bbox": [20, 20, 40, 60], "description": "A schematic diagram.",
         "status": "ok", "fragments": ["inside figure"]},
    ]


def test_visual_block_table_html_is_sanitized(tmp_path):
    put(tmp_path, "pymupdf", "d1", 1, blocks=[blk("pymupdf", type="title", text="T", order=0)])
    write_enrichment(PageEnrichment("d1", 1, "pymupdf", visual_blocks=[
        VisualBlock(type="table", label="table", bbox=[0, 0, 10, 10], position=0, crop_path="x.png",
                    content_text='<table><tr><td onclick="x()">a<script>1</script></td></tr></table>', content_source="vl"),
    ]), tmp_path)
    vb = page_data(doc(), 1, tmp_path)["visual_blocks"][0]
    assert vb["html"] == "<table><tr><td>a</td></tr></table>"


def test_visual_blocks_payload_empty_without_enrichment(tmp_path):
    assert _visual_blocks_payload("d1", 1, tmp_path) == []


def test_index_counts_half_filled(tmp_path):
    for p in (1, 2, 3, 4):
        put(tmp_path, "pymupdf", "d1", p)
    put(tmp_path, "vl", "d1", 1)
    put(tmp_path, "vl", "d1", 2, status="error", error="x")
    entries = [doc("d1"), doc("d2")]  # d2 has no results at all
    rows = index_data(entries, tmp_path)
    assert [r.entry.id for r in rows] == ["d1"]
    c = rows[0].counts
    assert c["pymupdf"] == {"ok": 4, "error": 0, "missing": 0}
    assert c["vl"] == {"ok": 1, "error": 1, "missing": 2}
    assert c["ocr"] == {"ok": 0, "error": 0, "missing": 4}
    assert set(c) == set(ENGINES)
