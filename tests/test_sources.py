import httpx

from docparse.dataset.sources import ntrs, nist, write_candidates
from docparse.dataset import manifest


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def ntrs_record(id, det="GOV_PUBLIC_USE_PERMITTED", dist="PUBLIC", third=False, pdf=True):
    return {
        "id": id, "title": f"Report {id}", "stiType": "OTHER", "distribution": dist,
        "copyright": {"determinationType": det, "containsThirdPartyMaterial": third},
        "downloads": [{"mimetype": "application/pdf", "links": {"pdf": f"/api/citations/{id}/downloads/{id}.pdf"}}] if pdf else [],
    }


def test_ntrs_maps_rights_and_skips_records_without_pdf():
    records = [ntrs_record(1), ntrs_record(2, third=True), ntrs_record(3, pdf=False), ntrs_record(4, dist="NASA_ONLY")]
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"results": records, "stats": {"total": 4}})

    found = ntrs.search(client_for(handler), "circuit", limit=10, tags="table;schematic")
    assert seen["q"] == "circuit"
    assert [e.id for e in found] == ["ntrs-1", "ntrs-2", "ntrs-4"]
    assert [e.rights for e in found] == ["public-domain", "unknown", "unknown"]
    assert found[0].url == "https://ntrs.nasa.gov/api/citations/1/downloads/1.pdf"
    assert found[0].group == "report" and found[0].tags == "table;schematic"


def test_ntrs_respects_limit_and_paginates():
    pages = []

    def handler(request):
        offset = int(request.url.params["page.from"])
        pages.append(offset)
        size = int(request.url.params["page.size"])
        return httpx.Response(200, json={"results": [ntrs_record(offset + i) for i in range(size)], "stats": {"total": 500}})

    found = ntrs.search(client_for(handler), "x", limit=150)
    assert len(found) == 150 and len(pages) >= 2


def test_nist_builds_doi_urls_and_ids():
    items = [{"DOI": "10.6028/nbs.tn.1164", "title": ["Photomask measurement"]}, {"DOI": "10.6028/x", "title": []}]
    handler = lambda request: httpx.Response(200, json={"message": {"items": items}})
    found = nist.search(client_for(handler), "photomask", limit=5, tags="plain-text")
    assert len(found) == 1
    e = found[0]
    assert (e.id, e.url, e.rights) == ("nist-nbs-tn-1164", "https://doi.org/10.6028/nbs.tn.1164", "public-domain")


def test_candidates_are_written_as_manifest_shaped_csv(tmp_path):
    handler = lambda request: httpx.Response(200, json={"results": [ntrs_record(1)], "stats": {"total": 1}})
    found = ntrs.search(client_for(handler), "x", limit=1)
    path = write_candidates("ntrs", found, tmp_path)
    assert manifest.load(path) == found
