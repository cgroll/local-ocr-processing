from docparse.dataset import manifest
from docparse.dataset.manifest import Entry


def make(**kw) -> Entry:
    base = dict(
        id="ds-001", url="https://example.org/a.pdf", group="datasheet", rights="vendor-copyright",
        rights_source="vendor site", tags="table;schematic",
    )
    return Entry(**{**base, **kw})


def test_complete_entry_is_valid():
    assert manifest.validate([make()]) == []


def test_missing_field_reports_line_and_name():
    errors = manifest.validate([make(), make(id="ds-002", rights_source="")])
    assert len(errors) == 1
    assert "line 3" in errors[0] and "'rights_source'" in errors[0]


def test_duplicate_id_reports_both_lines():
    errors = manifest.validate([make(), make()])
    assert len(errors) == 1
    assert "line 3" in errors[0] and "duplicate id 'ds-001'" in errors[0] and "line 2" in errors[0]


def test_unknown_enum_values_are_errors():
    errors = manifest.validate([make(group="misc", rights="free")])
    assert any("'group'" in e for e in errors) and any("'rights'" in e for e in errors)


def test_verified_fields_only_required_when_asked():
    assert manifest.validate([make()]) == []
    errors = manifest.validate([make()], require_verified=True)
    assert {"kind", "pages", "sha256"} == {e.split("'")[1] for e in errors}


def test_roundtrip(tmp_path):
    path = tmp_path / "m.csv"
    entries = [make(pages="12", kind="native", sha256="ab" * 32, title="Ä, \"quoted\"")]
    manifest.save(entries, path)
    assert manifest.load(path) == entries
