"""Batch run: engines one after another, pages in manifest order, one result file per engine and page."""
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..models import Registry
from .engines import PageJob, engine_version
from .executors import InProcessExecutor, JobSpec, WorkerExecutor
from .format import RESULTS_DIR, PageResult, read_result, result_path, write_result
from .render import DEFAULT_DPI, PAGES_DIR, page_image_path, render_page
from .select import DocPages

ENGINES = ("pymupdf", "layout", "ocr", "vl")


@dataclass
class Counts:
    done: int = 0
    skipped: int = 0
    errors: int = 0
    messages: list[str] = field(default_factory=list)


def default_executor(key: str, registry: Registry):
    if key == "vl":
        return WorkerExecutor(registry, timeout_s=registry.get("vl").params["timeout_s"])
    return InProcessExecutor(key, registry)


def _is_done(path: Path) -> bool:
    try:
        return path.exists() and read_result(path).status == "ok"
    except (OSError, ValueError, TypeError, KeyError):
        return False


def run_engine(
    key: str, docs: list[DocPages], registry: Registry, dpi: int = DEFAULT_DPI, force: bool = False,
    results_dir: Path = RESULTS_DIR, pages_dir: Path = PAGES_DIR,
    executor_factory: Callable = default_executor, log: Callable[[str], None] = print,
) -> Counts:
    counts = Counts()
    spec = registry.get(key)
    version = engine_version(key, spec.name)
    executor = None
    try:
        for doc in docs:
            for page in doc.pages:
                path = result_path(key, doc.doc_id, page, results_dir)
                if not force and _is_done(path):
                    counts.skipped += 1
                    continue
                png = page_image_path(doc.doc_id, page, pages_dir)
                job_spec = JobSpec(doc.doc_id, doc.pdf_path, page, dpi)
                result = PageResult(doc.doc_id, page, dpi, 0, 0, key, version)
                t0 = time.perf_counter()
                try:
                    rp = render_page(doc.pdf_path, page, dpi, None if png.exists() else png)
                    result.width, result.height = rp.width, rp.height
                    if executor is None:  # load the model only when something is left to do
                        executor = executor_factory(key, registry)
                        executor.start()
                    t0 = time.perf_counter()
                    result.blocks = executor.process(job_spec, PageJob(doc.doc_id, doc.pdf_path, page, rp))
                except Exception as e:  # one bad page must not stop the run
                    result.status, result.error = "error", f"{type(e).__name__}: {e}"
                    counts.errors += 1
                    counts.messages.append(f"{key} {doc.doc_id} p{page}: {result.error}")
                else:
                    counts.done += 1
                result.seconds = round(time.perf_counter() - t0, 2)
                write_result(result, results_dir)
                log(f"{key:8s} {doc.doc_id} p{page:<4d} {result.status:5s} {result.seconds:6.1f}s {len(result.blocks):4d} blocks")
    finally:
        if executor is not None:
            executor.close()
    return counts


def run_all(engines: list[str], docs: list[DocPages], registry: Registry, **kw) -> dict[str, Counts]:
    """Engines strictly one after another, so only one model is loaded at any time."""
    return {key: run_engine(key, docs, registry, **kw) for key in engines}
