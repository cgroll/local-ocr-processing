import httpx

from docparse.dataset.sources import seeds

SEED = """
# vendor datasheets
#! group=datasheet rights=vendor-copyright rights_source="vendor site" tags=table id_prefix=ds
https://vendor.example/lit/lm317.pdf | table;schematic | LM317 regulator
https://vendor.example/lit/lm317.pdf
#! group=scan rights=unknown rights_source="bitsavers (status unclear)" tags=schematic id_prefix=bs
https://bitsavers.example/pdf/dec/minc/
"""

INDEX = """<html><body>
<a href="?C=N;O=D">Name</a><a href="/pdf/dec/">Parent Directory</a>
<a href="Schematics_Jul78.pdf">x</a><a href="sub/">sub/</a><a href="notes.txt">n</a><a href="Manual%20A.PDF">m</a>
</body></html>"""


def client():
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=INDEX)))


def test_directives_apply_to_following_lines_and_ids_stay_unique():
    found = seeds.read(client(), SEED)
    by_id = {e.id: e for e in found}
    assert list(by_id) == ["ds-lm317", "ds-lm317-2", "bs-schematics-jul78", "bs-manual-a"]
    a = by_id["ds-lm317"]
    assert (a.group, a.rights, a.tags, a.title) == ("datasheet", "vendor-copyright", "table;schematic", "LM317 regulator")
    assert by_id["ds-lm317-2"].tags == "table"  # falls back to the directive default
    b = by_id["bs-schematics-jul78"]
    assert (b.group, b.rights, b.tags) == ("scan", "unknown", "schematic")
    assert b.rights_source == "bitsavers (status unclear)"


def test_directory_index_yields_only_direct_pdf_links():
    found = [e for e in seeds.read(client(), SEED) if e.id.startswith("bs-")]
    assert [e.url for e in found] == [
        "https://bitsavers.example/pdf/dec/minc/Schematics_Jul78.pdf",
        "https://bitsavers.example/pdf/dec/minc/Manual%20A.PDF",
    ]


def test_limit_caps_total_entries():
    assert len(seeds.read(client(), SEED, limit=3)) == 3
