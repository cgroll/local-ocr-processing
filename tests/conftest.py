import io
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import zipfile

import pymupdf
import pytest

from docparse.dataset.manifest import Entry


def make_pdf(pages: int = 2, text: bool = True, scan: bool = False) -> bytes:
    """Small PDF: text pages, or pages covered by one full-page image (a 'scan')."""
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        if scan:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
            pix.clear_with(200)
            page.insert_image(page.rect, pixmap=pix, keep_proportion=False)
        if text:
            page.insert_text((72, 100), f"Page {i + 1}: " + "lorem ipsum dolor sit amet " * 5)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def server():
    """Local HTTP server. Routes: /ok.pdf, /ok2.pdf, /error.html (200 + HTML), /big.pdf (2 MB), /pack.zip, /bad.zip, /missing (404)."""
    requests: list[tuple[str, float]] = []
    pdf = make_pdf(2)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("000/000001.pdf", pdf)
        zf.writestr("000/000002.pdf", make_pdf(3))
        zf.writestr("000/000003.txt", b"just text")
        zf.writestr("000/000004.pdf", b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024))
    routes = {
        "/ok.pdf": (200, "application/pdf", pdf),
        "/ok2.pdf": (200, "application/pdf", make_pdf(3)),
        "/error.html": (200, "text/html", b"<html><body>Access denied</body></html>"),
        "/pack.zip": (200, "application/zip", buf.getvalue()),
        "/bad.zip": (200, "application/zip", b"PK\x03\x04 this is not a real zip"),
        "/big.pdf": (200, "application/pdf", b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, time.monotonic()))
            status, ctype, body = routes.get(self.path, (404, "text/plain", b"not found"))
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield type("Server", (), {"base": base, "requests": requests, "ok_pdf": pdf})
    httpd.shutdown()


def entry(id: str, url: str, **kw) -> Entry:
    base = dict(group="datasheet", rights="unknown", rights_source="test", tags="table")
    return Entry(id=id, url=url, **{**base, **kw})
