"""NIST technical series (NBS/NIST reports), found via Crossref; https://doi.org/<doi> serves the PDF."""
import httpx

from ..manifest import Entry
from . import slug, tag_string

CROSSREF = "https://api.crossref.org/works"
NIST_PREFIX = "10.6028"
RIGHTS_SOURCE = "NIST technical series: US government work, https://www.nist.gov/open/license"


def search(client: httpx.Client, query: str, limit: int, tags: str = "") -> list[Entry]:
    r = client.get(CROSSREF, params={
        "filter": f"prefix:{NIST_PREFIX},type:report", "query": query, "rows": limit,
        "select": "DOI,title",
    })
    r.raise_for_status()
    entries = []
    for item in r.json()["message"]["items"]:
        titles = item.get("title") or []
        if not titles:
            continue
        doi = item["DOI"]
        entries.append(Entry(
            id=f"nist-{slug(doi.split('/', 1)[1])}", url=f"https://doi.org/{doi}", group="report",
            rights="public-domain", rights_source=RIGHTS_SOURCE, tags=tag_string(tags), title=" ".join(titles[0].split()),
        ))
    return entries
