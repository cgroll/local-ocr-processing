"""Generate the static viewer from manifest, page images and result files."""
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..dataset import manifest
from ..parse.format import RESULTS_DIR
from .data import index_data, page_data
from .templates import Nav, index_html, page_html

OUT_DIR = Path("data/viewer")
STATIC_DIR = Path(__file__).parent / "static"
PAGES_DIRNAME = "pages"  # sibling of the output directory; images are linked, not copied


@dataclass
class BuildReport:
    index: Path
    docs: int = 0
    pages: int = 0
    missing_images: list[str] = field(default_factory=list)


def _page_file(page: int) -> str:
    return f"{page:04d}.html"


def build(out_dir: Path = OUT_DIR, manifest_path: Path = manifest.DEFAULT_PATH,
          results_dir: Path = RESULTS_DIR, docs: set[str] | None = None) -> BuildReport:
    entries = [e for e in manifest.load(manifest_path) if not docs or e.id in docs]
    rows = index_data(entries, results_dir)
    pages_dir = out_dir.parent / PAGES_DIRNAME

    tmp = out_dir.with_name(out_dir.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "assets").mkdir(parents=True)
    for f in STATIC_DIR.iterdir():
        if f.is_file():
            shutil.copy2(f, tmp / "assets" / f.name)

    report = BuildReport(index=out_dir / "index.html", docs=len(rows))
    first_page = {r.entry.id: f"{r.entry.id}/{_page_file(r.with_results[0])}" for r in rows}
    for i, row in enumerate(rows):
        e = row.entry
        prev_doc = rows[i - 1] if i > 0 else None
        next_doc = rows[i + 1] if i + 1 < len(rows) else None
        (tmp / e.id).mkdir()
        for j, page in enumerate(row.with_results):
            data = page_data(e, page, results_dir)
            image = pages_dir / e.id / f"{page:04d}.png"
            if not image.exists():
                report.missing_images.append(f"{e.id}/{page:04d}.png")
            nav = Nav(
                index="../index.html",
                prev_page=_page_file(row.with_results[j - 1]) if j > 0 else None,
                next_page=_page_file(row.with_results[j + 1]) if j + 1 < len(row.with_results) else None,
                prev_doc=f"../{first_page[prev_doc.entry.id]}" if prev_doc else None,
                next_doc=f"../{first_page[next_doc.entry.id]}" if next_doc else None,
            )
            html = page_html(data, f"../../{PAGES_DIRNAME}/{e.id}/{image.name}", nav, tuple(row.with_results))
            (tmp / e.id / _page_file(page)).write_text(html, encoding="utf-8")
            report.pages += 1
    (tmp / "index.html").write_text(index_html(rows, first_page), encoding="utf-8")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    tmp.replace(out_dir)
    return report
