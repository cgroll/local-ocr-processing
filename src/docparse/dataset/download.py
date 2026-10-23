"""Download manifest documents into data/raw/<id>/, verify them and fill in missing manifest fields.

Downloaded files are untrusted: they are only ever opened with PyMuPDF, never executed.
"""
import hashlib
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx
import pymupdf

from .manifest import Entry

USER_AGENT = "docparse-dataset/0.1 (private research; sequential, rate-limited)"
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_PAGES = 6
DEFAULT_MIN_INTERVAL = 1.0
DEFAULT_MAX_ZIP_BYTES = 1024 * 1024 * 1024
PDF_FILENAME = "document.pdf"
CACHE_DIR = Path("data/cache")
PDF_MAGIC, ZIP_MAGIC = b"%PDF-", b"PK\x03\x04"

MIN_TEXT_CHARS = 50  # a page with less text than this has no usable text layer
SCAN_IMAGE_COVERAGE = 0.8  # an image covering this much of the page makes it a scan
NATIVE_RATIO, SCANNED_RATIO = 0.8, 0.2


class RejectedError(Exception):
    """The downloaded file is not acceptable as a dataset document."""


@dataclass
class Outcome:
    id: str
    status: str  # "downloaded" | "skipped" | "error"
    message: str = ""


class Throttle:
    """Keeps a minimum interval between requests to the same host (requests are sequential)."""

    def __init__(self, min_interval: float = DEFAULT_MIN_INTERVAL):
        self.min_interval = min_interval
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            delay = self.min_interval - (time.monotonic() - last)
            if delay > 0:
                time.sleep(delay)
        self._last[host] = time.monotonic()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(
    client: httpx.Client, url: str, dest: Path, max_bytes: int = DEFAULT_MAX_BYTES,
    magic: bytes = PDF_MAGIC, magic_window: int = 1024,
) -> None:
    """Stream url to dest via a .part file. Raises RejectedError for files without the magic bytes and oversized files."""
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with client.stream("GET", url, follow_redirects=True) as r:
            r.raise_for_status()
            declared = r.headers.get("content-length")
            if declared and int(declared) > max_bytes:
                raise RejectedError(f"file too large: {declared} bytes > limit {max_bytes}")
            size = 0
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    if size == 0 and magic not in chunk[:magic_window]:
                        kind = "PDF (missing %PDF- header)" if magic == PDF_MAGIC else "zip file"
                        raise RejectedError(f"not a {kind}")
                    size += len(chunk)
                    if size > max_bytes:
                        raise RejectedError(f"file too large: more than {max_bytes} bytes")
                    f.write(chunk)
        if size == 0:
            raise RejectedError("empty response")
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)


def split_zip_url(url: str) -> tuple[str, str] | None:
    """`<zip-url>#<entry>` -> (zip-url, entry), else None."""
    base, sep, member = url.partition("#")
    if sep and member and base.lower().endswith(".zip"):
        return base, member
    return None


def zip_cache_path(zip_url: str, cache_dir: Path = CACHE_DIR) -> Path:
    return cache_dir / PurePosixPath(urlparse(zip_url).path).name


def extract_member(zip_path: Path, member: str, dest: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    """Copy one zip entry to dest. The entry name is only a lookup key, never a path on disk."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            try:
                info = zf.getinfo(member)
            except KeyError:
                raise RejectedError(f"entry '{member}' not in {zip_path.name}") from None
            if info.file_size > max_bytes:
                raise RejectedError(f"entry too large: {info.file_size} bytes > limit {max_bytes}")
            size = 0
            with zf.open(info) as src, open(part, "wb") as out:
                while chunk := src.read(1 << 16):
                    if size == 0 and PDF_MAGIC not in chunk[:1024]:
                        raise RejectedError("not a PDF (missing %PDF- header)")
                    size += len(chunk)
                    if size > max_bytes:  # the declared size can lie
                        raise RejectedError(f"entry too large: more than {max_bytes} bytes")
                    out.write(chunk)
        if size == 0:
            raise RejectedError("empty entry")
        part.replace(dest)
    except zipfile.BadZipFile as exc:
        zip_path.unlink(missing_ok=True)  # a broken cached zip must not poison later runs
        raise RejectedError(f"bad zip file: {exc}") from exc
    finally:
        part.unlink(missing_ok=True)


def classify(doc: pymupdf.Document, first: int, last: int) -> str:
    """native / scanned / mixed from the share of pages with a text layer (1-based, inclusive).

    A page counts as scanned when a single image covers most of it, even if it carries a hidden
    OCR text layer, because the text there is not native.
    """
    native = 0
    for i in range(first - 1, last):
        page = doc[i]
        area = page.rect.width * page.rect.height
        scan_like = any(
            pymupdf.Rect(info["bbox"]).intersect(page.rect).get_area() >= SCAN_IMAGE_COVERAGE * area
            for info in page.get_image_info()
        )
        has_text = len(page.get_text().strip()) >= MIN_TEXT_CHARS
        native += has_text and not scan_like
    ratio = native / (last - first + 1)
    if ratio >= NATIVE_RATIO:
        return "native"
    if ratio <= SCANNED_RATIO:
        return "scanned"
    return "mixed"


def ingest(entry: Entry, pdf: Path, max_pages: int = DEFAULT_MAX_PAGES) -> None:
    """Verify pdf against entry (hash, page count); fill in missing sha256, pages, page_range, kind.

    Raises RejectedError on mismatch or an unreadable file.
    """
    digest = sha256_of(pdf)
    if entry.sha256 and entry.sha256 != digest:
        raise RejectedError(f"sha256 mismatch: manifest {entry.sha256[:12]}…, file {digest[:12]}…")
    try:
        with pymupdf.open(pdf) as doc:
            if doc.needs_pass:
                raise RejectedError("PDF is encrypted")
            pages = len(doc)
            if entry.pages and int(entry.pages) != pages:
                raise RejectedError(f"page count mismatch: manifest {entry.pages}, file {pages}")
            if pages == 0:
                raise RejectedError("PDF has no pages")
            if not entry.page_range and pages > max_pages:
                entry.page_range = f"1-{max_pages}"
            first, last = (int(x) for x in entry.page_range.split("-")) if entry.page_range else (1, pages)
            if not entry.kind:
                entry.kind = classify(doc, first, min(last, pages))
    except RejectedError:
        raise
    except Exception as exc:  # PyMuPDF raises various errors for broken files
        raise RejectedError(f"unreadable PDF: {exc}") from exc
    entry.sha256 = digest
    entry.pages = str(pages)


def process(
    entry: Entry,
    client: httpx.Client,
    throttle: Throttle,
    raw_root: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_pages: int = DEFAULT_MAX_PAGES,
    cache_dir: Path = CACHE_DIR,
    max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES,
) -> Outcome:
    pdf = raw_root / entry.id / PDF_FILENAME
    try:
        if pdf.exists():
            if entry.sha256 and sha256_of(pdf) == entry.sha256:
                return Outcome(entry.id, "skipped")
            status = "skipped"  # file placed by hand (no hash yet) is verified, not downloaded
            if entry.sha256:
                raise RejectedError("local file does not match manifest sha256; remove it to re-download")
        else:
            if zipref := split_zip_url(entry.url):
                zip_url, member = zipref
                zip_path = zip_cache_path(zip_url, cache_dir)
                if not zip_path.exists():  # fetched once, shared by all entries of this zip
                    throttle.wait(urlparse(zip_url).netloc)
                    fetch(client, zip_url, zip_path, max_zip_bytes, ZIP_MAGIC, 4)
                extract_member(zip_path, member, pdf, max_bytes)
            else:
                throttle.wait(urlparse(entry.url).netloc)
                fetch(client, entry.url, pdf, max_bytes)
            status = "downloaded"
        try:
            ingest(entry, pdf, max_pages)
        except RejectedError:
            if status == "downloaded":
                pdf.replace(pdf.with_name(pdf.name + ".rejected"))  # never offered to later steps
            raise
        return Outcome(entry.id, status)
    except RejectedError as exc:
        return Outcome(entry.id, "error", str(exc))
    except httpx.HTTPError as exc:
        return Outcome(entry.id, "error", f"{type(exc).__name__}: {exc}")


def download_all(
    entries: list[Entry],
    raw_root: Path = Path("data/raw"),
    min_interval: float = DEFAULT_MIN_INTERVAL,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_pages: int = DEFAULT_MAX_PAGES,
    only: set[str] | None = None,
    cache_dir: Path = CACHE_DIR,
    max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES,
) -> list[Outcome]:
    throttle = Throttle(min_interval)
    outcomes = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60) as client:
        for entry in entries:
            if only is not None and entry.id not in only:
                continue
            outcomes.append(process(entry, client, throttle, raw_root, max_bytes, max_pages, cache_dir, max_zip_bytes))
    for entry in entries:  # zips are only a transport: drop them once the run is over
        if (zipref := split_zip_url(entry.url)) and (only is None or entry.id in only):
            zip_cache_path(zipref[0], cache_dir).unlink(missing_ok=True)
    return outcomes
