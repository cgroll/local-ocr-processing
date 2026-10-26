"""Batch run: enrich every selected page with a chosen text source, narrative text, and crops +
descriptions for its figure/chart/table blocks. Resumable like `docparse.parse run`: existing
`ok` results are skipped, a failing block does not stop its page or the run, `--force` recomputes
everything."""
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..models.lifecycle import ModelManager
from ..parse.render import PAGES_DIR, page_image_path
from ..parse.select import DocPages
from . import blocks as B
from . import describe as D
from .format import PageEnrichment, RESULTS_DIR as ENRICH_RESULTS_DIR, VisualBlock, crop_path, read_result, result_path, write_result


@dataclass
class Counts:
    done: int = 0
    skipped: int = 0
    errors: int = 0  # page-level failures (no text source, missing page image)
    block_errors: int = 0  # individual crop/description failures that did not fail the page
    messages: list[str] = field(default_factory=list)


def _is_done(path: Path) -> bool:
    try:
        return path.exists() and read_result(path).status == "ok"
    except (OSError, ValueError, TypeError, KeyError):
        return False


def enrich_page(
    doc: DocPages, page: int, manager: ModelManager | None, results_dir: Path, pages_dir: Path,
) -> tuple[PageEnrichment, int]:
    """Returns (result, block_errors). `manager` may be None to skip descriptions (tests)."""
    t0 = time.perf_counter()
    text_source, source_result = B.choose_text_source(doc.doc_id, page, results_dir)
    if source_result is None:
        return PageEnrichment(
            doc.doc_id, page, text_source, status="error",
            error="no usable text source (pymupdf and ocr both missing or failed)",
            seconds=round(time.perf_counter() - t0, 2),
        ), 0

    png = page_image_path(doc.doc_id, page, pages_dir)
    if not png.exists():
        return PageEnrichment(
            doc.doc_id, page, text_source, narrative_text=B.narrative_text(source_result),
            status="error", error=f"page image missing: {png}",
            seconds=round(time.perf_counter() - t0, 2),
        ), 0

    layout_result = B.read_ok("layout", doc.doc_id, page, results_dir)
    candidates = B.visual_candidates(layout_result) if layout_result else []
    pymupdf_result = B.read_ok("pymupdf", doc.doc_id, page, results_dir)
    vl_result = B.read_ok("vl", doc.doc_id, page, results_dir)

    visual_blocks: list[VisualBlock] = []
    block_errors = 0
    table_rank = 0
    for c in candidates:
        content_text = content_source = None
        if c.type == "table":
            content_text, content_source = B.table_content(table_rank, pymupdf_result, vl_result)
            table_rank += 1

        out_path = crop_path(doc.doc_id, page, c.type, c.position, results_dir)
        vb = VisualBlock(
            type=c.type, label=c.label, bbox=c.bbox, position=c.position, crop_path=str(out_path),
            content_text=content_text, content_source=content_source,
        )
        try:
            image = B.crop_region(png, c.bbox)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(out_path)
            if manager is not None:
                vb.description = D.describe(manager, image, c.type)
        except Exception as e:  # one bad block must not stop the page or the run
            vb.status, vb.error = "error", f"{type(e).__name__}: {e}"
            block_errors += 1
        visual_blocks.append(vb)

    result = PageEnrichment(
        doc.doc_id, page, text_source, narrative_text=B.narrative_text(source_result),
        visual_blocks=visual_blocks, seconds=round(time.perf_counter() - t0, 2),
    )
    return result, block_errors


def run(
    docs: list[DocPages], manager: ModelManager | None, force: bool = False,
    results_dir: Path = ENRICH_RESULTS_DIR, pages_dir: Path = PAGES_DIR,
    log=print,
) -> Counts:
    counts = Counts()
    for doc in docs:
        for page in doc.pages:
            path = result_path(doc.doc_id, page, results_dir)
            if not force and _is_done(path):
                counts.skipped += 1
                continue
            result, block_errors = enrich_page(doc, page, manager, results_dir, pages_dir)
            counts.block_errors += block_errors
            if result.status == "error":
                counts.errors += 1
                counts.messages.append(f"{doc.doc_id} p{page}: {result.error}")
            else:
                counts.done += 1
            write_result(result, results_dir)
            log(
                f"enrich   {doc.doc_id} p{page:<4d} {result.status:5s} {result.seconds:6.1f}s "
                f"{len(result.visual_blocks):3d} visual blocks ({block_errors} errors)"
            )
    return counts
