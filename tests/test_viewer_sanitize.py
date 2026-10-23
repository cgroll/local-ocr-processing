import json
from pathlib import Path

import pytest

from docparse.viewer.sanitize import sanitize_table

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
