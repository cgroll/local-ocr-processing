"""Seed lists: hand-curated URLs (vendor datasheets, Bitsavers) in datasets/seeds/*.txt.

Format, one item per line:
    #! group=datasheet rights=vendor-copyright rights_source="vendor site" tags=table;diagram id_prefix=ds
    https://example.com/part.pdf | table;schematic | optional title
    https://bitsavers.org/pdf/dec/pdp11/minc/        <- trailing '/' = directory index, every PDF in it
`#!` lines set defaults (shell quoting for values with spaces) for the lines below them; `#` lines are comments.
"""
import shlex
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

import httpx

from ..manifest import Entry
from . import slug, tag_string

DIRECTIVES = {"group", "rights", "rights_source", "tags", "id_prefix"}


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def pdf_links(index_html: str, base_url: str) -> list[str]:
    """PDF files linked directly from a directory index (no sub-directories, no sort links)."""
    parser = _Links()
    parser.feed(index_html)
    out = []
    for href in parser.hrefs:
        if href.startswith("?") or "/" in href.strip("/") or not href.lower().endswith(".pdf"):
            continue
        out.append(urljoin(base_url, href))
    return out


def parse(text: str) -> list[tuple[dict, str, str, str]]:
    """Return (defaults, url, tags, title) per item line."""
    defaults: dict[str, str] = {}
    items = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#!"):
            for token in shlex.split(line[2:]):
                key, _, value = token.partition("=")
                if key in DIRECTIVES:
                    defaults[key] = value
            continue
        if line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        items.append((dict(defaults), parts[0], parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else ""))
    return items


def read(client: httpx.Client, text: str, limit: int | None = None) -> list[Entry]:
    entries: list[Entry] = []
    used: set[str] = set()
    for defaults, url, tags, title in parse(text):
        urls = [(url, title)]
        if url.endswith("/"):
            r = client.get(url)
            r.raise_for_status()
            urls = [(u, "") for u in pdf_links(r.text, url)]
        for u, t in urls:
            stem = PurePosixPath(unquote(urlparse(u).path)).stem
            base = f"{defaults.get('id_prefix', 'seed')}-{slug(stem)}"
            id, n = base, 2
            while id in used:
                id, n = f"{base}-{n}", n + 1
            used.add(id)
            entries.append(Entry(
                id=id, url=u, group=defaults.get("group", ""), rights=defaults.get("rights", "unknown"),
                rights_source=defaults.get("rights_source", "seed list default"),
                tags=tag_string(tags or defaults.get("tags", "")), title=t or stem,
            ))
            if limit and len(entries) >= limit:
                return entries
    return entries
