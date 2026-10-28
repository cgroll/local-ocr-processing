import json
from pathlib import Path

import pytest

from docparse.viewer.sanitize import sanitize_markdown_html, sanitize_table

FIXTURES = Path(__file__).parent / "fixtures"


def test_real_vl_table_keeps_structure_and_text():
    raw = json.loads((FIXTURES / "vl_table_raw.json").read_text(encoding="utf-8"))
    html = next(b["content"] for b in raw["blocks"] if b["label"] == "table")
    out = sanitize_table(html)
    assert out.startswith("<table><tr><td>DEVICE PINOUT</td>")
    assert out.count("<tr>") == html.count("<tr>")
    assert out.count("</td>") == html.count("</td>")
    assert "INITIAL ACCURACY" in out


def test_spans_kept_when_numeric():
    out = sanitize_table('<table><tr><td rowspan="2" colspan=3>x</td></tr></table>')
    assert out == '<table><tr><td rowspan="2" colspan="3">x</td></tr></table>'


@pytest.mark.parametrize("attr", ['colspan="x"', 'colspan="-1"', 'colspan="2 onclick=1"', 'colspan="99999"', 'colspan="０"'])
def test_bad_span_values_dropped(attr):
    assert sanitize_table(f"<table><tr><td {attr}>x</td></tr></table>") == "<table><tr><td>x</td></tr></table>"


@pytest.mark.parametrize("html, forbidden", [
    ("<table><tr><td><script>alert(1)</script>ok</td></tr></table>", ["script", "alert"]),
    ('<table><tr><td><img src=x onerror=alert(1)>ok</td></tr></table>', ["img", "onerror", "src"]),
    ('<table><tr><td><a href="javascript:alert(1)">ok</a></td></tr></table>', ["<a", "href", "javascript"]),
    ('<table onclick="alert(1)"><tr><td onmouseover="x()" style="a:b">ok</td></tr></table>', ["onclick", "onmouseover", "style"]),
    ("<table><tr><td><style>td{background:url(http://evil)}</style>ok</td></tr></table>", ["style", "evil"]),
    ('<table><tr><td><iframe src="http://evil"></iframe>ok</td></tr></table>', ["iframe", "evil"]),
])
def test_attack_patterns_removed(html, forbidden):
    out = sanitize_table(html)
    assert "ok" in out
    for word in forbidden:
        assert word not in out


def test_text_is_escaped():
    out = sanitize_table("<table><tr><td>a &lt;b&gt; &amp; c</td></tr></table>")
    assert out == "<table><tr><td>a &lt;b&gt; &amp; c</td></tr></table>"


def test_unclosed_and_stray_tags_balanced():
    out = sanitize_table("<table><tr><td>a<td>b</tr></div></table")
    assert out.count("<td>") == out.count("</td>")
    assert out.endswith("</table>")


def test_br_kept():
    assert "<br>" in sanitize_table("<table><tr><td>a<br/>b</td></tr></table>")


# --- sanitize_markdown_html: extended allow-list for Markdown-rendered pages (viewer-markdown-view) ----

def test_markdown_headings_lists_and_emphasis_kept():
    html = "<h3>Title</h3><p>Some <strong>bold</strong> and <em>italic</em> text.</p><ul><li>one</li><li>two</li></ul>"
    assert sanitize_markdown_html(html) == html


def test_markdown_table_kept():
    html = "<table><thead><tr><th>a</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>"
    assert sanitize_markdown_html(html) == html


def test_markdown_code_and_blockquote_kept():
    html = "<pre><code>x = 1</code></pre><blockquote>quoted</blockquote>"
    assert sanitize_markdown_html(html) == html


def test_markdown_script_tag_dropped():
    out = sanitize_markdown_html("<p>ok</p><script>alert(1)</script>")
    assert out == "<p>ok</p>"


def test_markdown_links_and_images_dropped():
    # No real use case for links/images in narrative/VLM-description text -- deliberately not
    # in MARKDOWN_TAGS, so both the tag and (for <img>, which has no text content) its attributes
    # are gone; for <a>, the enclosed link text survives as plain escaped text.
    out = sanitize_markdown_html('<p>see <a href="javascript:alert(1)">this</a></p><img src=x onerror=alert(1)>')
    assert "href" not in out and "javascript" not in out and "<a" not in out
    assert "<img" not in out and "onerror" not in out
    assert "this" in out  # link text itself is not attacker-controlled markup, kept as text


def test_markdown_does_not_leak_table_only_sanitizer_difference():
    # sanitize_table (TABLE_TAGS) must NOT accept headings -- confirms the two allow-lists are
    # genuinely distinct, not accidentally merged into one shared global. The <h3> tag itself is
    # dropped like any other disallowed-but-harmless tag (text content is kept, same as the
    # existing "stray tag" behavior covered by test_unclosed_and_stray_tags_balanced).
    assert sanitize_table("<h3>Title</h3><table><tr><td>x</td></tr></table>") == "Title<table><tr><td>x</td></tr></table>"


# --- Markdown sections: <div data-section="n"> (viewer-layout-markdown-link) -------------

def test_section_div_keeps_numeric_index():
    assert sanitize_markdown_html('<div data-section="3"><p>x</p></div>') == '<div data-section="3"><p>x</p></div>'


def test_section_index_zero_is_kept():
    assert sanitize_markdown_html('<div data-section="0"></div>') == '<div data-section="0"></div>'


@pytest.mark.parametrize("value", ['"x"', '"-1"', '"1.5"', '""', '"1e3"', '"١"', '"99999999"'])
def test_section_index_must_be_plain_non_negative_integer(value):
    out = sanitize_markdown_html(f"<div data-section={value}><p>x</p></div>")
    assert "data-section" not in out
    assert "<div>" in out and "<p>x</p>" in out


def test_section_attribute_only_on_div():
    out = sanitize_markdown_html('<p data-section="1">x</p>')
    assert out == "<p>x</p>"


def test_foreign_attributes_on_div_are_dropped():
    out = sanitize_markdown_html('<div class="a" onclick="b()" data-section="2" style="c">t</div>')
    assert out == '<div data-section="2">t</div>'


def test_script_inside_section_is_dropped():
    out = sanitize_markdown_html('<div data-section="1"><script>alert(1)</script><p>ok</p></div>')
    assert "script" not in out and "alert" not in out
    assert out == '<div data-section="1"><p>ok</p></div>'


def test_table_sanitizer_does_not_keep_section_div():
    assert sanitize_table('<div data-section="1"><table><tr><td>v</td></tr></table></div>') == \
        "<table><tr><td>v</td></tr></table>"


def test_rowspan_still_kept_on_table_cells_only():
    out = sanitize_markdown_html('<table><tr><td rowspan="2">v</td></tr></table>')
    assert '<td rowspan="2">v</td>' in out
    assert "rowspan" not in sanitize_markdown_html('<div rowspan="2">v</div>')
