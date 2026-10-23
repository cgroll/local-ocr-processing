from docparse.dataset import manifest
from docparse.dataset.__main__ import main
from conftest import entry


def setup(tmp_path):
    cand = tmp_path / "cand.csv"
    manifest.save([entry(f"c{i}", f"https://x/{i}.pdf") for i in range(3)], cand)
    return cand, tmp_path / "m.csv"


def test_add_takes_only_named_candidates(tmp_path):
    cand, m = setup(tmp_path)
    assert main(["--manifest", str(m), "add", str(cand), "c0", "c2"]) == 0
    assert [e.id for e in manifest.load(m)] == ["c0", "c2"]


def test_add_is_idempotent_and_rejects_unknown_ids(tmp_path, capsys):
    cand, m = setup(tmp_path)
    main(["--manifest", str(m), "add", str(cand), "c1"])
    assert main(["--manifest", str(m), "add", str(cand), "c1"]) == 0
    assert [e.id for e in manifest.load(m)] == ["c1"]
    assert main(["--manifest", str(m), "add", str(cand), "nope"]) == 1
    assert "nope" in capsys.readouterr().out
    assert [e.id for e in manifest.load(m)] == ["c1"]
