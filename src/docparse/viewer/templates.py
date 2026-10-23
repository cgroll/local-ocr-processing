"""HTML shells for the index and page views; all dynamic behaviour lives in static/*.js."""
from dataclasses import dataclass
from html import escape

from .data import ENGINES, DocCoverage, embed_json

CSP = "default-src 'none'; img-src 'self' data:; style-src 'self'; script-src 'self'"


@dataclass
class Nav:
    """Relative links (from the page file) for one page view; None where there is no target."""
    index: str
    prev_page: str | None = None
    next_page: str | None = None
    prev_doc: str | None = None
    next_doc: str | None = None


def _head(title: str, assets: str, script: str) -> str:
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f'<link rel="stylesheet" href="{assets}/style.css">\n'
        f'<script src="{assets}/{script}" defer></script>\n</head>\n'
    )


def _link(rel: str, label: str, href: str | None) -> str:
    if href is None:
        return f'<span class="nav-off">{label}</span>'
    return f'<a rel="{rel}" href="{escape(href)}">{label}</a>'


def page_html(data: dict, image_href: str, nav: Nav, pages: tuple[int, ...] = ()) -> str:
    title = f"{data['title']} – page {data['page']}"
    links = " ".join([
        _link("index", "Index", nav.index),
        _link("prev-doc", "&laquo; doc", nav.prev_doc),
        _link("prev", "&lsaquo; page", nav.prev_page),
        _link("next", "page &rsaquo;", nav.next_page),
        _link("next-doc", "doc &raquo;", nav.next_doc),
    ])
    return (
        _head(title, "../assets", "page.js")
        + '<body class="page-view">\n'
        f'<header class="bar"><nav>{links}</nav>'
        f'<h1>{escape(data["title"])} <small>{escape(data["doc"])} · page {data["page"]}</small></h1></header>\n'
        f'<main id="app" data-image="{escape(image_href)}" data-pages="{",".join(map(str, pages))}"></main>\n'
        f'<script type="application/json" id="page-data">{embed_json(data)}</script>\n'
        "</body>\n</html>\n"
    )


def index_html(rows: list[DocCoverage], first_page_href: dict[str, str]) -> str:
    groups = sorted({r.entry.group for r in rows})
    tags = sorted({t for r in rows for t in r.entry.tag_list})
    opts = lambda values: "".join(f'<option value="{escape(v)}">{escape(v)}</option>' for v in values)
    head_cols = "".join(f'<th class="eng-{e}">{e}</th>' for e in ENGINES)
    body = []
    for r in rows:
        e = r.entry
        cells = "".join(
            f'<td class="cov eng-{eng}">{_coverage_cell(r.counts[eng])}</td>' for eng in ENGINES
        )
        search = " ".join([e.id, e.title, e.group, e.tags]).lower()
        body.append(
            f'<tr data-group="{escape(e.group)}" data-tags="{escape(";" + e.tags + ";")}" data-search="{escape(search)}">'
            f'<td><a href="{escape(first_page_href[e.id])}">{escape(e.title or e.id)}</a><br><small>{escape(e.id)}</small></td>'
            f"<td>{escape(e.group)}</td><td>{escape(' '.join(e.tag_list))}</td><td>{escape(e.kind)}</td>"
            f"<td>{len(r.pages)}</td>{cells}</tr>"
        )
    return (
        _head("Parse results", "assets", "index.js")
        + '<body class="index-view">\n<header class="bar"><h1>Parse results</h1></header>\n<main>\n'
        '<form class="filters">'
        f'<label>Group <select id="f-group"><option value="">all</option>{opts(groups)}</select></label> '
        f'<label>Tag <select id="f-tag"><option value="">all</option>{opts(tags)}</select></label> '
        '<label>Search <input id="f-text" type="search" placeholder="title or id"></label> '
        '<span id="f-count"></span></form>\n'
        '<p class="legend">Per engine: pages <b>ok</b> / <b>error</b> / <b>missing</b></p>\n'
        f'<table id="docs"><thead><tr><th>Document</th><th>Group</th><th>Tags</th><th>Kind</th><th>Pages</th>{head_cols}</tr></thead>\n'
        f'<tbody>\n{chr(10).join(body)}\n</tbody></table>\n</main>\n</body>\n</html>\n'
    )


def _coverage_cell(c: dict[str, int]) -> str:
    err = f'<span class="n-error">{c["error"]}</span>' if c["error"] else "0"
    miss = f'<span class="n-missing">{c["missing"]}</span>' if c["missing"] else "0"
    return f'<span class="n-ok">{c["ok"]}</span> / {err} / {miss}'
