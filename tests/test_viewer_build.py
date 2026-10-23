from docparse.dataset import manifest
from docparse.dataset.manifest import Entry
from docparse.parse.format import Block, PageResult, write_result
from docparse.viewer.__main__ import main
from docparse.viewer.build import build


def setup_data(tmp_path):
    results = tmp_path / "results"
    entries = [
        Entry(id="a", group="datasheet", tags="table", title="A", pages="3", page_range="1-3"),
        Entry(id="b", group="scan", tags="schematic", title="B", pages="2", page_range="1-2"),
        Entry(id="c", group="scan", tags="x", title="C", pages="2", page_range="1-2"),  # no results
    ]
    manifest.save(entries, tmp_path / "manifest.csv")
    for doc, pages in (("a", [1, 3]), ("b", [1, 2])):
        for p in pages:
            blocks = [Block(type="text", label="text", bbox=[1, 1, 5, 5], engine="pymupdf", text="x")]
            write_result(PageResult(doc, p, 150, 50, 50, "pymupdf", blocks=blocks), results)
    (tmp_path / "pages" / "a").mkdir(parents=True)
    (tmp_path / "pages" / "a" / "0001.png").write_bytes(b"png")
    return results


def test_build_writes_index_pages_assets(tmp_path):
    results = setup_data(tmp_path)
    out = tmp_path / "viewer"
    (out / "gone").mkdir(parents=True)  # leftovers of an earlier run must disappear
    report = build(out, tmp_path / "manifest.csv", results)
    assert report.docs == 2 and report.pages == 4
    assert (out / "index.html").exists() and not (out / "gone").exists()
    assert (out / "assets" / "page.js").exists() and (out / "assets" / "style.css").exists()
    assert sorted(p.name for p in (out / "a").iterdir()) == ["0001.html", "0003.html"]
    assert not (tmp_path / "viewer.tmp").exists()
    assert "b/0001.png" in report.missing_images[0] or any("b/" in m for m in report.missing_images)
    assert "a/0003.png" in report.missing_images


def test_navigation_crosses_pages_and_documents(tmp_path):
    results = setup_data(tmp_path)
    out = tmp_path / "viewer"
    build(out, tmp_path / "manifest.csv", results)
    first_a = (out / "a" / "0001.html").read_text()
    last_a = (out / "a" / "0003.html").read_text()
    assert 'rel="next" href="0003.html"' in first_a  # page 2 has no result and is skipped
    assert 'rel="next-doc" href="../b/0001.html"' in last_a
    assert 'rel="prev-doc"' not in first_a
    assert 'rel="prev-doc" href="../a/0001.html"' in (out / "b" / "0001.html").read_text()
    assert 'data-image="../../pages/a/0001.png"' in first_a


def test_docs_filter_and_sources_untouched(tmp_path, capsys):
    results = setup_data(tmp_path)
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    out = tmp_path / "viewer"
    rc = main(["build", "--docs", "b", "--out-dir", str(out), "--manifest", str(tmp_path / "manifest.csv"),
               "--results-dir", str(results)])
    assert rc == 0
    assert not (out / "a").exists() and (out / "b").exists()
    assert str((out / "index.html").resolve()) in capsys.readouterr().out
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file() and "viewer" not in p.parts)
    assert after == before


def test_page_jump_list_embedded(tmp_path):
    results = setup_data(tmp_path)
    out = tmp_path / "viewer"
    build(out, tmp_path / "manifest.csv", results)
    assert 'data-pages="1,3"' in (out / "a" / "0001.html").read_text()
