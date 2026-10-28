"""Reduce untrusted HTML to an allow-listed tag subset (rebuilt from parsed tokens, not a
regex/blocklist) -- `sanitize_table` for engine-supplied table HTML, `sanitize_markdown_html`
for HTML rendered from digest Markdown (viewer-markdown-view). Both share one parser: safety
comes from only ever emitting tags in the given allow-list, regardless of how a disallowed tag
reached the parser (hand-written HTML, or passed through unchanged by the `markdown` library's
raw-HTML handling) -- never from trusting the input's own escaping."""
from html import escape
from html.parser import HTMLParser

TABLE_TAGS = {"table", "thead", "tbody", "tr", "td", "th"}
# Superset of TABLE_TAGS: digest Markdown renders to headings/paragraphs/lists/emphasis/code in
# addition to the tables `html_table_to_markdown` already produces. No `a`/`img`: no real use
# case in VLM-description/narrative text, and skipping them avoids href/src validation entirely.
MARKDOWN_TAGS = TABLE_TAGS | {
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "li",
    "strong", "em", "code", "pre", "blockquote", "div",
}
ALLOWED_TAGS = TABLE_TAGS  # backward-compatible alias; sanitize_table's allow-list
VOID_TAGS = {"br"}
DROP_CONTENT = {"script", "style", "template", "noscript"}
SPAN_ATTRS = {"rowspan", "colspan"}
MAX_SPAN = 1000
# Markdown sections of a page (viewer-layout-markdown-link): `<div data-section="<index>">`, the only
# attribute the Markdown view keeps. The index is a plain non-negative integer, bounded.
SECTION_TAG = "div"
SECTION_ATTR = "data-section"
MAX_SECTION_INDEX = 100_000


def _is_plain_int(value: str | None, lo: int, hi: int) -> bool:
    return bool(value) and value.isascii() and value.isdigit() and lo <= int(value) <= hi


class _Sanitizer(HTMLParser):
    def __init__(self, allowed_tags: set[str]):
        super().__init__(convert_charrefs=True)
        self.allowed_tags = allowed_tags
        self.out: list[str] = []
        self.open: list[str] = []
        self.dropping: str | None = None  # tag whose content is being discarded

    def handle_starttag(self, tag, attrs):
        if self.dropping:
            return
        if tag in DROP_CONTENT:
            self.dropping = tag
        elif tag in VOID_TAGS:
            self.out.append("<br>")
        elif tag in self.allowed_tags:
            kept = "".join(
                f' {k}="{v}"' for k, v in attrs
                if (tag in TABLE_TAGS and k in SPAN_ATTRS and _is_plain_int(v, 1, MAX_SPAN))
                or (tag == SECTION_TAG and k == SECTION_ATTR and _is_plain_int(v, 0, MAX_SECTION_INDEX))
            )
            self.out.append(f"<{tag}{kept}>")
            self.open.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in VOID_TAGS:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.dropping:
            if tag == self.dropping:
                self.dropping = None
            return
        if tag in self.allowed_tags and tag in self.open:
            while self.open:
                self.out.append(f"</{(top := self.open.pop())}>")
                if top == tag:
                    break

    def handle_data(self, data):
        if not self.dropping:
            self.out.append(escape(data, quote=False))

    def close(self):
        super().close()
        while self.open:
            self.out.append(f"</{self.open.pop()}>")


def _sanitize(html: str, allowed_tags: set[str]) -> str:
    parser = _Sanitizer(allowed_tags)
    parser.feed(html)
    parser.close()
    return "".join(parser.out)


def sanitize_table(html: str) -> str:
    """Return html reduced to table structure with rowspan/colspan; text is escaped, everything else dropped."""
    return _sanitize(html, TABLE_TAGS)


def sanitize_markdown_html(html: str) -> str:
    """Return html reduced to the Markdown-view tag subset (headings/paragraphs/lists/emphasis/
    code/tables); text is escaped, everything else (including `a`/`img`) dropped."""
    return _sanitize(html, MARKDOWN_TAGS)
