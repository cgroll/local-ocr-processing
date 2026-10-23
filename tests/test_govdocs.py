import zipfile

from docparse.dataset.sources import govdocs

BIG = b"%PDF-1.4\n" + b"0" * 20_000


def make_zip(path):
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(40):
            zf.writestr(f"000/{i:06d}.pdf", BIG)
        zf.writestr("000/000100.doc", BIG)
        zf.writestr("000/000101.pdf", b"%PDF-tiny")  # below the size floor
    return path


def test_same_seed_gives_same_sample_and_different_seed_differs(tmp_path):
    z = make_zip(tmp_path / "000.zip")
    a = govdocs.sample(z, "000", 8, seed=1)
    b = govdocs.sample(z, "000", 8, seed=1)
    c = govdocs.sample(z, "000", 8, seed=2)
    assert a == b and [e.id for e in a] != [e.id for e in c]


def test_sample_contains_only_sized_pdfs_with_zip_member_urls(tmp_path):
    z = make_zip(tmp_path / "000.zip")
    found = govdocs.sample(z, "000", 100, seed=1, tags="plain-text")
    assert len(found) == 40
    assert all(e.url.startswith(govdocs.ZIP_BASE + "000.zip#000/") and e.url.endswith(".pdf") for e in found)
    assert all(e.rights == "open-license" and e.group == "corpus-sample" and e.tags == "plain-text" for e in found)
    assert len({e.id for e in found}) == 40
