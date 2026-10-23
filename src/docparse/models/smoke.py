"""Smoke test: load each model in turn, run one tiny inference, unload, report timings and VRAM."""
import multiprocessing as mp
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .gpu import PeakSampler, gpu_memory_mb
from .lifecycle import ModelManager
from .registry import Registry

SMOKE_DPI = 150
LOAD_TIMEOUT_S = 900  # first run downloads weights


@dataclass
class Sample:
    image: np.ndarray  # BGR, as Paddle expects
    pdf_path: Path | None


@dataclass
class SmokeResult:
    key: str
    ok: bool
    load_s: float = 0.0
    infer_s: float = 0.0
    peak_mb: int = 0
    residual_mb: int | None = None  # GPU memory still used after unload, relative to before load
    detail: str = ""


def make_sample(raw_dir: Path = Path("data/raw")) -> Sample:
    """First page of the first downloaded document, or a synthetic text page without data."""
    import pymupdf

    pdfs = sorted(raw_dir.glob("*/document.pdf")) if raw_dir.exists() else []
    if pdfs:
        with pymupdf.open(pdfs[0]) as doc:
            pix = doc[0].get_pixmap(dpi=SMOKE_DPI, colorspace=pymupdf.csRGB)
        pdf_path = pdfs[0]
    else:
        with pymupdf.open() as doc:
            doc.new_page().insert_text((72, 100), "Smoke test page\nResistor R1 10 kOhm", fontsize=18)
            pix = doc[0].get_pixmap(dpi=SMOKE_DPI, colorspace=pymupdf.csRGB)
        pdf_path = None
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return Sample(np.ascontiguousarray(rgb[:, :, ::-1]), pdf_path)


def infer(key: str, handle, sample: Sample, params: dict) -> str:
    if key == "pymupdf":
        if sample.pdf_path is None:
            return "synthetic page, no PDF opened"
        with handle.open(sample.pdf_path) as doc:
            return f"{len(doc[0].get_text())} chars of text layer"
    if key == "ocr":
        res = handle.predict(sample.image)
        return f"{len(res[0]['rec_texts'])} text lines"
    if key == "layout":
        res = handle.predict(sample.image)
        return f"{len(res[0]['boxes'])} layout blocks"
    if key == "vl":
        res = handle.predict(sample.image, max_new_tokens=params["max_new_tokens"])
        return f"{len(res[0].markdown['markdown_texts'])} chars of markdown"
    if key == "embedding":
        vec = handle.encode("Smoke test", prompt_name="Document")
        return f"vector of {vec.shape[-1]} dims"
    raise KeyError(key)


def _timed_run(registry: Registry, key: str, sample: Sample, report) -> None:
    """Load, infer and unload `key`; `report(event, *payload)` is called after load and at the end."""
    manager = ModelManager(registry)
    spec = registry.get(key)
    try:
        t0 = time.perf_counter()
        handle = manager.load(key)
        load_s = time.perf_counter() - t0
        report("loaded", load_s)
        t1 = time.perf_counter()
        detail = infer(key, handle, sample, spec.params)
        report("inferred", time.perf_counter() - t1, detail)
        del handle
    finally:
        manager.unload_all()


def _worker(registry, key, sample, conn):
    try:
        _timed_run(registry, key, sample, lambda *msg: conn.send(msg))
        conn.send(("done",))
    except Exception as e:  # reported to the parent, which decides the exit code
        conn.send(("error", f"{type(e).__name__}: {e}"))
    finally:
        conn.close()


def _run_in_child(registry: Registry, key: str, sample: Sample) -> tuple[float, float, str]:
    """Run in a child process so a stuck generation can be killed and its VRAM is freed on exit."""
    timeout_s = registry.get(key).params["timeout_s"]
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_worker, args=(registry, key, sample, child), daemon=True)
    proc.start()
    child.close()
    load_s = infer_s = 0.0
    detail = ""
    deadline = time.monotonic() + LOAD_TIMEOUT_S
    try:
        while True:
            if not parent.poll(max(0.0, deadline - time.monotonic())):
                what = "inference" if load_s else "loading"
                raise TimeoutError(f"{what} exceeded the limit of {timeout_s if load_s else LOAD_TIMEOUT_S} s")
            try:
                msg = parent.recv()
            except EOFError:
                raise RuntimeError("worker process died without a result") from None
            if msg[0] == "loaded":
                load_s = msg[1]
                deadline = time.monotonic() + timeout_s  # per-page limit starts after loading
            elif msg[0] == "inferred":
                infer_s, detail = msg[1], msg[2]
            elif msg[0] == "error":
                raise RuntimeError(msg[1])
            elif msg[0] == "done":
                break
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join()
    return load_s, infer_s, detail


def run_smoke(registry: Registry, keys: list[str], sample: Sample) -> list[SmokeResult]:
    results = []
    for key in keys:
        before = gpu_memory_mb()
        result = SmokeResult(key, ok=False)
        sampler = PeakSampler()
        try:
            ModelManager(registry).check(key)
            with sampler:
                if key == "vl":
                    result.load_s, result.infer_s, result.detail = _run_in_child(registry, key, sample)
                else:
                    times = {}
                    _timed_run(registry, key, sample, lambda ev, *p: times.update({ev: p}))
                    result.load_s = times["loaded"][0]
                    result.infer_s, result.detail = times["inferred"]
            result.ok = True
        except Exception as e:  # one failing model must not stop the others
            result.detail = f"{type(e).__name__}: {e}"
        time.sleep(1)  # let the driver settle before reading the residual
        after = gpu_memory_mb()
        if before and after:
            result.peak_mb = max(0, sampler.peak_mb - before[0])
            result.residual_mb = after[0] - before[0]
        results.append(result)
    return results
