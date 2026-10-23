"""GovDocs1 (Digital Corpora): random sample of PDFs from one of the zip packages.

GovDocs1 is only published as zips of ~1000 mixed files, so a sample is drawn from the zip's
file list. Candidate URLs have the form <zip-url>#<entry>; the download step reads the entries
from the same cached zip and deletes it afterwards.
"""
import random
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from .. import download
from ..manifest import Entry
from . import tag_string

ZIP_BASE = "https://digitalcorpora.s3.amazonaws.com/corpora/files/govdocs1/zipfiles/"
RIGHTS_SOURCE = "GovDocs1 (Digital Corpora): freely redistributable US government web documents"
MIN_BYTES, MAX_BYTES = 10 * 1024, 20 * 1024 * 1024  # skip stubs and very large files


def ensure_zip(client: httpx.Client, name: str, cache_dir: Path = download.CACHE_DIR) -> Path:
    """Download <name>.zip into the cache unless it is already there."""
    url = f"{ZIP_BASE}{name}.zip"
    path = download.zip_cache_path(url, cache_dir)
    if not path.exists():
        download.fetch(client, url, path, download.DEFAULT_MAX_ZIP_BYTES, download.ZIP_MAGIC, 4)
    return path


def sample(zip_path: Path, zip_name: str, count: int, seed: int, tags: str = "") -> list[Entry]:
    with zipfile.ZipFile(zip_path) as zf:
        members = sorted(
            i.filename for i in zf.infolist()
            if i.filename.lower().endswith(".pdf") and MIN_BYTES <= i.file_size <= MAX_BYTES
        )
    picked = sorted(random.Random(seed).sample(members, min(count, len(members))))
    return [
        Entry(
            id=f"gd1-{PurePosixPath(m).stem}", url=f"{ZIP_BASE}{zip_name}.zip#{m}", group="corpus-sample",
            rights="open-license", rights_source=RIGHTS_SOURCE, tags=tag_string(tags),
            title=PurePosixPath(m).name,
        )
        for m in picked
    ]


def search(client: httpx.Client, zip_name: str, count: int, seed: int, tags: str = "",
           cache_dir: Path = download.CACHE_DIR) -> list[Entry]:
    return sample(ensure_zip(client, zip_name, cache_dir), zip_name, count, seed, tags)
