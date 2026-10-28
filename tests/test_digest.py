from pathlib import Path

from docparse.digest import document as D
from docparse.digest import markdown as M
from docparse.digest import page as P
from docparse.digest import runner as R
from docparse.enrich.format import PageEnrichment, VisualBlock, write_result as write_enrichment
from docparse.parse.format import Block, PageResult, write_result as write_engine_result

DOC = "ds-example"


def _engine_block(type_, text, bbox, order=0):
    return Block(type=type_, label=type_, bbox=bbox, engine="pymupdf", order=order, text=text)


def _write_engine(root, engine, page, blocks, status="ok"):
    write_engine_result(PageResult(DOC, page, 150, 1275, 1650, engine, status=status, blocks=blocks), root)


# --- render_narrative_block ---------------------------------------------------

def test_render_narrative_block_by_type():
    assert M.render_narrative_block(_engine_block("title", "Intro", [0, 0, 1, 1])) == "### Intro"
    assert M.render_narrative_block(_engine_block("caption", "Fig. 1", [0, 0, 1, 1])) == "*Fig. 1*"
    assert M.render_narrative_block(_engine_block("list", "a\nb", [0, 0, 1, 1])) == "- a\n- b"
    assert M.render_narrative_block(_engine_block("text", "plain", [0, 0, 1, 1])) == "plain"


def test_render_narrative_block_empty_text_is_empty_string():
    assert M.render_narrative_block(_engine_block("text", "   ", [0, 0, 1, 1])) == ""


# --- html_table_to_markdown ----------------------------------------------------

def test_simple_table_to_markdown():
    html = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"
    md = M.html_table_to_markdown(html)
    assert md == "| a | b |\n| --- | --- |\n| c | d |"


def test_rowspan_repeats_value_into_every_covered_row():
    # The ds-lm317-style case: a leftmost cell spans 2 rows.
    html = (
        "<table>"
        "<tr><td rowspan=\"2\">1.5A</td><td>Input voltage</td></tr>"
        "<tr><td>PSRR</td></tr>"
        "</table>"
    )
    md = M.html_table_to_markdown(html)
    rows = md.splitlines()
    assert rows[0] == "| 1.5A | Input voltage |"
    assert rows[2] == "| 1.5A | PSRR |"  # rowspan carries "1.5A" down into the next row


def test_colspan_repeats_value_across_columns():
    html = "<table><tr><td colspan=\"2\">wide</td></tr><tr><td>a</td><td>b</td></tr></table>"
    md = M.html_table_to_markdown(html)
    assert md.splitlines()[0] == "| wide | wide |"


def test_cell_with_newline_becomes_br_and_pipe_is_escaped():
    html = "<table><tr><td>a\nb</td><td>c|d</td></tr></table>"
    md = M.html_table_to_markdown(html)
    assert "a<br>b" in md and "c\\|d" in md


def test_empty_table_is_empty_string():
    assert M.html_table_to_markdown("<table></table>") == ""


# --- overlapping_fragments ------------------------------------------------------

def test_overlapping_fragment_is_found():
    target = [100.0, 100.0, 200.0, 200.0]
    candidates = [_engine_block("text", "VOS", [110.0, 110.0, 130.0, 120.0])]
    assert M.overlapping_fragments(target, candidates) == ["VOS"]


def test_non_overlapping_fragment_is_excluded():
    target = [100.0, 100.0, 200.0, 200.0]
    candidates = [_engine_block("text", "far away", [500.0, 500.0, 600.0, 600.0])]
    assert M.overlapping_fragments(target, candidates) == []


def test_fragments_are_deduplicated_and_ordered_top_to_bottom():
    target = [0.0, 0.0, 300.0, 300.0]
    candidates = [
        _engine_block("text", "second", [10.0, 50.0, 50.0, 60.0]),
        _engine_block("text", "first", [10.0, 10.0, 50.0, 20.0]),
        _engine_block("text", "first", [60.0, 10.0, 90.0, 20.0]),  # duplicate text, dropped
    ]
    assert M.overlapping_fragments(target, candidates) == ["first", "second"]


def test_empty_text_blocks_are_ignored():
    target = [0.0, 0.0, 100.0, 100.0]
    candidates = [_engine_block("image", "", [10.0, 10.0, 20.0, 20.0])]
    assert M.overlapping_fragments(target, candidates) == []


def test_enclosing_text_blob_is_not_attached_to_a_small_figure():
    """A small figure fully contained in one big text block (e.g. a native PDF reporting a whole
    table as a single text blob) must NOT inherit that blob's text: only a tiny fraction of the
    blob's own box is inside the figure. Regression for the smaller-box ratio (ratio was 1.0)."""
    figure = [819.0, 848.0, 1003.0, 1099.0]
    candidates = [_engine_block("text", "whole table as one blob", [132.0, 352.0, 1194.0, 1129.0])]
    assert M.overlapping_fragments(figure, candidates) == []


def test_small_label_inside_figure_is_still_kept():
    """The flip side: a genuine small label whose box lies inside the figure is still collected."""
    figure = [819.0, 848.0, 1003.0, 1099.0]
    candidates = [_engine_block("line", "B1", [899.0, 1064.0, 913.0, 1078.0])]
    assert M.overlapping_fragments(figure, candidates) == ["B1"]


# --- assign_fragments (exclusive, one text -> at most one component) --------------

def test_assign_fragments_is_exclusive_across_overlapping_targets():
    """A text that geometrically falls into two overlapping components is assigned only to the one it
    sits in most, not to both."""
    a = [0.0, 0.0, 100.0, 100.0]
    b = [50.0, 0.0, 200.0, 100.0]  # overlaps `a` in x 50..100
    # a label almost entirely inside `a` (only a sliver reaches into the overlap zone)
    label = _engine_block("text", "VOS", [10.0, 10.0, 55.0, 30.0])
    out = M.assign_fragments([a, b], [label])
    assert out == [["VOS"], []]


def test_assign_fragments_picks_the_higher_overlap_target():
    a = [0.0, 0.0, 100.0, 100.0]
    b = [60.0, 0.0, 160.0, 100.0]
    # label box x 70..130 (own width 60): 30 wide inside `a` (70..100, ratio 0.5), 60 wide inside
    # `b` (70..130, ratio 1.0) -> assigned to b
    label = _engine_block("text", "x", [70.0, 10.0, 130.0, 30.0])
    assert M.assign_fragments([a, b], [label]) == [[], ["x"]]


def test_assign_fragments_tie_breaks_to_first_target():
    # identical boxes -> identical overlap ratios; the earlier target wins
    a = [0.0, 0.0, 100.0, 100.0]
    b = [0.0, 0.0, 100.0, 100.0]
    label = _engine_block("text", "tie", [10.0, 10.0, 40.0, 40.0])
    assert M.assign_fragments([a, b], [label]) == [["tie"], []]


def test_assign_fragments_respects_threshold():
    a = [0.0, 0.0, 100.0, 100.0]
    # only ~10% of the label's own box is inside `a` -> below the 0.3 threshold, dropped
    label = _engine_block("text", "edge", [90.0, 90.0, 190.0, 190.0])
    assert M.assign_fragments([a], [label]) == [[]]


def test_assign_fragments_enclosing_blob_not_attached():
    """Same regression as overlapping_fragments: a figure inside one giant text blob gets nothing."""
    figure = [819.0, 848.0, 1003.0, 1099.0]
    table = [100.0, 100.0, 1100.0, 1100.0]  # the big text blob, also a (table) target
    blob = _engine_block("text", "whole table blob", [132.0, 352.0, 1194.0, 1129.0])
    out = M.assign_fragments([figure, table], [blob])
    assert out == [[], ["whole table blob"]]  # blob belongs to the table, not the figure


def test_assign_fragment_boxes_keeps_each_fragments_own_box():
    target = [0.0, 0.0, 100.0, 100.0]
    lower = _engine_block("text", "lower", [10.0, 50.0, 40.0, 60.0])
    upper = _engine_block("text", "upper", [10.0, 10.0, 40.0, 20.0])
    out = M.assign_fragment_boxes([target], [lower, upper])
    assert out == [[("upper", [10.0, 10.0, 40.0, 20.0]), ("lower", [10.0, 50.0, 40.0, 60.0])]]


def test_assign_fragment_boxes_text_matches_assign_fragments():
    target = [0.0, 0.0, 100.0, 100.0]
    frags = [_engine_block("text", "a", [10.0, 10.0, 40.0, 20.0]),
             _engine_block("text", "a", [10.0, 30.0, 40.0, 40.0]),  # duplicate text: first box kept
             _engine_block("text", "b", [50.0, 50.0, 80.0, 60.0])]
    boxes = M.assign_fragment_boxes([target], frags)
    assert [[t for t, _ in b] for b in boxes] == M.assign_fragments([target], frags)
    assert boxes == [[("a", [10.0, 10.0, 40.0, 20.0]), ("b", [50.0, 50.0, 80.0, 60.0])]]


# --- page.render_page -----------------------------------------------------------

def test_render_page_includes_heading_description_table_and_fragments(tmp_path):
    source = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=[
        _engine_block("title", "My Title", [0, 0, 10, 10], order=0),
        _engine_block("text", "VOS", [110.0, 110.0, 130.0, 120.0], order=1),
    ])
    _write_engine(tmp_path, "pymupdf", 1, source.blocks)
    enrichment = PageEnrichment(DOC, 1, "pymupdf", narrative_text="unused", visual_blocks=[
        VisualBlock(type="table", label="table", bbox=[100.0, 100.0, 200.0, 200.0], position=0,
                    crop_path="x.png", description="a table about X",
                    content_text="<table><tr><td>v</td></tr></table>", content_source="pymupdf"),
    ])
    rendered = P.render_page(enrichment, source, tmp_path)
    assert "## Seite 1" in rendered
    assert "### My Title" in rendered
    assert "### Tabelle: table" in rendered
    assert "a table about X" in rendered
    assert "| v |" in rendered
    assert M.TABLE_STRUCTURE_WARNING in rendered
    assert "VOS" in rendered  # overlapping fragment picked up


def test_render_page_skips_failed_visual_blocks(tmp_path):
    source = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=[])
    _write_engine(tmp_path, "pymupdf", 1, [])
    enrichment = PageEnrichment(DOC, 1, "pymupdf", visual_blocks=[
        VisualBlock(type="figure", label="image", bbox=[0, 0, 1, 1], position=0,
                    crop_path="x.png", status="error", error="boom"),
    ])
    rendered = P.render_page(enrichment, source, tmp_path)
    assert "boom" not in rendered and "Abbildung" not in rendered


def test_render_page_falls_back_to_narrative_text_without_source(tmp_path):
    enrichment = PageEnrichment(DOC, 1, "pymupdf", narrative_text="fallback text")
    rendered = P.render_page(enrichment, None, tmp_path)
    assert "fallback text" in rendered


# --- document.render_document / write_digest -------------------------------------

def _two_page_doc(tmp_path):
    for page, text in [(1, "page one"), (2, "page two")]:
        _write_engine(tmp_path, "pymupdf", page, [_engine_block("text", text, [0, 0, 10, 10])])
        write_enrichment(PageEnrichment(DOC, page, "pymupdf", narrative_text=text), tmp_path)


def test_render_document_concatenates_pages_in_order_with_doc_title(tmp_path):
    _two_page_doc(tmp_path)
    md = D.render_document(DOC, tmp_path)
    assert md.startswith(f"# {DOC}")
    assert md.index("## Seite 1") < md.index("page one") < md.index("## Seite 2") < md.index("page two")


def test_render_document_skips_error_pages(tmp_path):
    _write_engine(tmp_path, "pymupdf", 1, [_engine_block("text", "ok page", [0, 0, 10, 10])])
    write_enrichment(PageEnrichment(DOC, 1, "pymupdf", narrative_text="ok page"), tmp_path)
    write_enrichment(PageEnrichment(DOC, 2, "none", status="error", error="no text source"), tmp_path)
    md = D.render_document(DOC, tmp_path)
    assert "ok page" in md and "Seite 2" not in md


def test_write_digest_is_deterministic_across_reruns(tmp_path):
    _two_page_doc(tmp_path)
    path1 = D.write_digest(DOC, tmp_path)
    text1 = path1.read_text()
    path2 = D.write_digest(DOC, tmp_path)
    assert path1 == path2 == D.digest_path(DOC, tmp_path)
    assert text1 == path2.read_text()


def test_runner_handles_a_document_with_no_enriched_pages(tmp_path):
    _two_page_doc(tmp_path)
    counts = R.run([DOC, "missing-doc"], tmp_path, log=lambda *a: None)
    assert counts.done == 2 and counts.errors == 0  # a doc with no enriched pages just yields an empty digest
    assert D.digest_path("missing-doc", tmp_path).read_text().strip() == "# missing-doc"


def test_render_page_places_visual_in_page_order_with_caption_after_description(tmp_path):
    """A figure sits between the text above and below it (not appended at the end), and the text in
    the layout `caption` box next to it becomes its caption instead of staying in the narrative."""
    source = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=[
        _engine_block("text", "ABOVE", [100, 100, 600, 150], order=0),
        _engine_block("text", "Figure 1. Pinout", [100, 520, 600, 550], order=1),
        _engine_block("text", "BELOW", [100, 700, 600, 750], order=2),
    ])
    _write_engine(tmp_path, "pymupdf", 1, source.blocks)
    _write_engine(tmp_path, "layout", 1, [
        Block(type="caption", label="caption", bbox=[90, 515, 610, 555], engine="layout", order=0),
    ])
    enrichment = PageEnrichment(DOC, 1, "pymupdf", visual_blocks=[
        VisualBlock(type="figure", label="image", bbox=[100, 200, 600, 510], position=0,
                    crop_path="x.png", description="a pinout drawing"),
    ])
    rendered = P.render_page(enrichment, source, tmp_path)
    order = [rendered.index(t) for t in ("ABOVE", "### Abbildung: image", "a pinout drawing", "*Figure 1. Pinout*", "BELOW")]
    assert order == sorted(order)
    assert rendered.count("Figure 1. Pinout") == 1  # moved out of the narrative, not duplicated


def test_render_page_visual_stays_in_its_column(tmp_path):
    """Two-column page: a figure in the right column is not slipped in between left-column text."""
    blocks = [_engine_block("text", f"L{i}", [100, 100 + i * 150, 500, 150 + i * 150], order=i) for i in range(5)]
    blocks += [_engine_block("text", f"R{i}", [800, 100 + i * 150, 1200, 150 + i * 150], order=5 + i) for i in range(5)]
    source = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=blocks)
    _write_engine(tmp_path, "pymupdf", 1, blocks)
    enrichment = PageEnrichment(DOC, 1, "pymupdf", visual_blocks=[
        VisualBlock(type="figure", label="image", bbox=[800, 400, 1200, 520], position=0, crop_path="x.png"),
    ])
    rendered = P.render_page(enrichment, source, tmp_path)
    assert rendered.index("L4") < rendered.index("R0") < rendered.index("R2") < rendered.index("### Abbildung") < rendered.index("R3")


def test_pymupdf_table_without_visual_block_stays_in_the_narrative(tmp_path):
    """pymupdf finds a "table" in ruled text (table of contents) that layout sees as text, so no visual
    block covers it. Its text must not vanish; one a visual block does cover is left to that block."""
    toc = Block(type="table", label="table", bbox=[100, 200, 600, 400], engine="pymupdf", order=0,
                text="1\tFeatures", html="<table><tr><td>1</td><td>Features</td></tr></table>")
    covered = Block(type="table", label="table", bbox=[100, 800, 600, 900], engine="pymupdf", order=1,
                    text="X\tY", html="<table><tr><td>X</td><td>Y</td></tr></table>")
    source = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=[
        toc, covered, _engine_block("text", "HEAD", [100, 100, 600, 150], order=2),
        _engine_block("text", "TAIL", [100, 1000, 600, 1050], order=3),
    ])
    _write_engine(tmp_path, "pymupdf", 1, source.blocks)
    enrichment = PageEnrichment(DOC, 1, "pymupdf", visual_blocks=[
        VisualBlock(type="table", label="table", bbox=[90, 790, 610, 910], position=0, crop_path="x.png",
                    content_text="<table><tr><td>X</td><td>Y</td></tr></table>", content_source="pymupdf"),
    ])
    rendered = P.render_page(enrichment, source, tmp_path)
    assert rendered.index("HEAD") < rendered.index("Features") < rendered.index("### Tabelle") < rendered.index("TAIL")
    assert rendered.count("| X | Y |") == 1  # covered table appears once, via its visual block


def test_render_page_table_with_content_has_no_raw_fragments(tmp_path):
    """A table with recognised content already carries its text; the found-text list would repeat it."""
    source = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=[
        _engine_block("text", "cell text", [110.0, 110.0, 130.0, 120.0], order=0),
    ])
    _write_engine(tmp_path, "pymupdf", 1, source.blocks)
    enrichment = PageEnrichment(DOC, 1, "pymupdf", visual_blocks=[
        VisualBlock(type="table", label="table", bbox=[100.0, 100.0, 200.0, 200.0], position=0, crop_path="x.png",
                    content_text="<table><tr><td>v</td></tr></table>", content_source="vl"),
    ])
    rendered = P.render_page(enrichment, source, tmp_path)
    assert "| v |" in rendered and M.RAW_FRAGMENTS_LABEL not in rendered


def test_visuals_are_placed_by_position_even_if_the_engine_lists_the_footer_first(tmp_path):
    """pymupdf lists footer text first; figures in a text-free right column (grid, two per row) must
    land after the heading above them, in row order, not at the top."""
    blocks = [
        _engine_block("text", "FOOTER", [100, 1580, 1200, 1620], order=0),
        _engine_block("text", "LEFT", [100, 200, 500, 800], order=1),
        _engine_block("text", "RIGHTHEAD", [650, 185, 880, 220], order=2),
    ]
    source = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=blocks)
    _write_engine(tmp_path, "pymupdf", 1, blocks)
    figs = [("A", [695, 260, 930, 500]), ("B", [945, 260, 1190, 500]), ("C", [717, 584, 894, 800])]
    enrichment = PageEnrichment(DOC, 1, "pymupdf", visual_blocks=[
        VisualBlock(type="figure", label="image", bbox=bb, position=i, crop_path="x.png", description=f"fig {n}")
        for i, (n, bb) in enumerate(figs)
    ])
    r = P.render_page(enrichment, source, tmp_path)
    idx = [r.index(t) for t in ("RIGHTHEAD", "fig A", "fig B", "fig C")]
    assert idx == sorted(idx)


def test_text_follows_the_layout_models_reading_order(tmp_path):
    """The layout model's `order` decides the sequence, not the text engine's: here the engine lists
    the right column and the footer first; layout says left column, right column, and gives the footer
    (and figures) no order. Unordered blocks and figures are placed by position."""
    blocks = [
        _engine_block("text", "FOOTER", [100, 1580, 1200, 1620], order=0),
        _engine_block("text", "RIGHT", [650, 200, 1100, 300], order=1),
        _engine_block("text", "LEFT", [100, 200, 500, 300], order=2),
    ]
    source = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=blocks)
    _write_engine(tmp_path, "pymupdf", 1, blocks)
    _write_engine(tmp_path, "layout", 1, [
        Block(type="text", label="text", bbox=[90, 190, 510, 310], engine="layout", order=1),
        Block(type="text", label="text", bbox=[640, 190, 1110, 310], engine="layout", order=2),
        Block(type="footer", label="footer", bbox=[90, 1570, 1210, 1630], engine="layout", order=None),
        Block(type="figure", label="image", bbox=[650, 400, 1100, 600], engine="layout", order=None),
    ])
    enrichment = PageEnrichment(DOC, 1, "pymupdf", visual_blocks=[
        VisualBlock(type="figure", label="image", bbox=[650, 400, 1100, 600], position=0, crop_path="x.png", description="fig"),
    ])
    r = P.render_page(enrichment, source, tmp_path)
    idx = [r.index(t) for t in ("LEFT", "RIGHT", "### Abbildung", "FOOTER")]
    assert idx == sorted(idx)


# --- page.render_page_sections ---------------------------------------------------

def _figure_page(tmp_path):
    source = PageResult(DOC, 1, 150, 1275, 1650, "pymupdf", blocks=[
        _engine_block("text", "ABOVE", [100, 100, 600, 150], order=0),
        _engine_block("text", "Figure 1. Pinout", [100, 520, 600, 550], order=1),
        _engine_block("text", "VOS", [150, 300, 200, 320], order=2),
        _engine_block("text", "BELOW", [100, 700, 600, 750], order=3),
    ])
    _write_engine(tmp_path, "pymupdf", 1, source.blocks)
    _write_engine(tmp_path, "layout", 1, [
        Block(type="caption", label="caption", bbox=[90, 515, 610, 555], engine="layout", order=0),
    ])
    enrichment = PageEnrichment(DOC, 1, "pymupdf", visual_blocks=[
        VisualBlock(type="figure", label="image", bbox=[100, 200, 600, 510], position=0,
                    crop_path="x.png", description="a pinout drawing"),
    ])
    return enrichment, source


def test_render_page_is_the_join_of_its_sections(tmp_path):
    enrichment, source = _figure_page(tmp_path)
    sections = P.render_page_sections(enrichment, source, tmp_path)
    assert all(s.text for s in sections)
    expected = "\n\n".join([f"## Seite 1"] + [s.text for s in sections])
    assert P.render_page(enrichment, source, tmp_path) == expected


def test_narrative_section_carries_its_block_box(tmp_path):
    enrichment, source = _figure_page(tmp_path)
    sections = P.render_page_sections(enrichment, source, tmp_path)
    above = next(s for s in sections if s.text == "ABOVE")
    assert above.bboxes == [[100, 100, 600, 150]]


def test_visual_section_carries_visual_caption_and_fragment_boxes(tmp_path):
    enrichment, source = _figure_page(tmp_path)
    sections = P.render_page_sections(enrichment, source, tmp_path)
    figure = next(s for s in sections if s.text.startswith("### Abbildung"))
    assert [100, 200, 600, 510] in figure.bboxes  # the visual block itself
    assert [100, 520, 600, 550] in figure.bboxes  # its caption
    assert [150, 300, 200, 320] in figure.bboxes  # the fragment placed under it
    assert "*Figure 1. Pinout*" in figure.text and "VOS" in figure.text
