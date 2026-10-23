"""NASA Technical Reports Server (https://ntrs.nasa.gov/api)."""
import httpx

from ..manifest import Entry
from . import tag_string

BASE = "https://ntrs.nasa.gov"
SEARCH = f"{BASE}/api/citations/search"
PUBLIC_USE = "GOV_PUBLIC_USE_PERMITTED"
MAX_REQUESTS = 20


def rights_of(record: dict) -> tuple[str, str]:
    """public-domain only when NTRS marks the record public, public-use-permitted and free of third-party material."""
    c = record.get("copyright") or {}
    det = c.get("determinationType", "NOT_SET")
    if record.get("distribution") == "PUBLIC" and det == PUBLIC_USE and not c.get("containsThirdPartyMaterial"):
        return "public-domain", f"NTRS copyright.determinationType={det}"
    return "unknown", f"NTRS distribution={record.get('distribution')} determinationType={det}"


def pdf_link(record: dict) -> str | None:
    for d in record.get("downloads") or []:
        if d.get("mimetype") == "application/pdf" and d.get("links", {}).get("pdf"):
            return BASE + d["links"]["pdf"]
    return None


def search(client: httpx.Client, query: str, limit: int, tags: str = "") -> list[Entry]:
    entries: list[Entry] = []
    offset, size = 0, min(max(limit * 2, 25), 100)
    for _ in range(MAX_REQUESTS):
        r = client.get(SEARCH, params={"q": query, "page.size": size, "page.from": offset})
        r.raise_for_status()
        data = r.json()
        for rec in data.get("results", []):
            url = pdf_link(rec)
            if not url:
                continue
            rights, source = rights_of(rec)
            entries.append(Entry(
                id=f"ntrs-{rec['id']}", url=url, group="report", rights=rights, rights_source=source,
                tags=tag_string(tags), title=rec.get("title", ""),
                notes=f"stiType={rec.get('stiType', '')}",
            ))
            if len(entries) >= limit:
                return entries
        offset += size
        if offset >= data.get("stats", {}).get("total", 0):
            break
    return entries
