from docparse.dataset.manifest import Entry
from docparse.dataset.summary import summarize


def make(i, group, tags, kind="native", pages="10") -> Entry:
    return Entry(id=f"d{i}", url="u", group=group, rights="unknown", rights_source="x",
                 tags=tags, kind=kind, pages=pages)


def test_small_manifest_triggers_group_and_tag_warnings():
    entries = [make(1, "datasheet", "table;schematic"), make(2, "datasheet", "table", kind="scanned")]
    report, warnings = summarize(entries)
    assert "2 documents, 20 pages" in report
    assert any("group 'report'" in w for w in warnings)
    assert any("tag 'formula'" in w for w in warnings)
    assert any("tag 'table'" in w for w in warnings)  # 2 < 5
    assert "native=1, scanned=1" in report


def test_full_manifest_has_no_warnings():
    targets = {"datasheet": 20, "report": 20, "scan": 10, "corpus-sample": 20}
    tags = "table;schematic;diagram;formula;plain-text"
    entries = [make(f"{g}{i}", g, tags) for g, n in targets.items() for i in range(n)]
    report, warnings = summarize(entries)
    assert warnings == []
    assert "<- gap" not in report
