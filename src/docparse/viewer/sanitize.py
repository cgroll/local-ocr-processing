"""Reduce untrusted table HTML to plain table structure (allow-list, rebuilt from parsed tokens)."""
from html import escape
from html.parser import HTMLParser

ALLOWED_TAGS = {"table", "thead", "tbody", "tr", "td", "th"}
VOID_TAGS = {"br"}
DROP_CONTENT = {"script", "style", "template", "noscript"}
SPAN_ATTRS = {"rowspan", "colspan"}
MAX_SPAN = 1000


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
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
        elif tag in ALLOWED_TAGS:
            kept = "".join(
                f' {k}="{v}"' for k, v in attrs
                if k in SPAN_ATTRS and v and v.isascii() and v.isdigit() and 0 < int(v) <= MAX_SPAN
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
        if tag in ALLOWED_TAGS and tag in self.open:
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


def sanitize_table(html: str) -> str:
    """Return html reduced to table structure with rowspan/colspan; text is escaped, everything else dropped."""
    parser = _Sanitizer()
    parser.feed(html)
    parser.close()
    return "".join(parser.out)
