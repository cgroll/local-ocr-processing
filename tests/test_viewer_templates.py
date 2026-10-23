import re

from docparse.dataset.manifest import Entry
from docparse.viewer.data import ENGINES, DocCoverage
from docparse.viewer.templates import Nav, index_html, page_html


def external(html: str) -> list[str]:
    return re.findall(r'(?:src|href)="((?:[a-z]+:)?//[^"]+)"', html)


def inline_scripts(html: str) -> list[str]:
    tags = re.findall(r"<script\b([^>]*)>", html)
    return [t for t in tags if "src=" not in t and 'type="application/json"' not in t]


def test_page_shell_is_offline_and_script_free():
    data = {"doc": "d1", "title": "A <b>doc</b>", "page": 2, "size": [10, 10], "engines": {}}
    html = page_html(data, "../../pages/d1/0002.png", Nav("../index.html", prev_page="0001.html", next_doc="../d2/0001.html"))
    assert external(html) == []
    assert inline_scripts(html) == []
    assert 'http-equiv="Content-Security-Policy"' in html
    assert "script-src 'self'" in html and "default-src 'none'" in html
    assert 'src="../assets/page.js"' in html and 'href="../assets/style.css"' in html
    assert "A <b>doc</b>" not in html and "A &lt;b&gt;doc&lt;/b&gt;" in html
    assert 'rel="prev"' in html and 'rel="next-doc"' in html
    assert 'rel="next"' not in html  # no target -> plain label


def test_index_shell():
    e = Entry(id="d1", title="T&C", group="datasheet", tags="table;schematic", kind="native", pages="5")
    counts = {x: {"ok": 1, "error": 0, "missing": 2} for x in ENGINES}
    html = index_html([DocCoverage(e, [1, 2, 3], counts, [1])], {"d1": "d1/0001.html"})
    assert external(html) == [] and inline_scripts(html) == []
    assert "T&amp;C" in html and 'data-tags=";table;schematic;"' in html
    assert 'href="d1/0001.html"' in html
    assert "onsubmit" not in html  # inline handlers are blocked by the CSP anyway
