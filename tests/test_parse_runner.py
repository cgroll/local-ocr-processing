import time
from pathlib import Path

import pymupdf
import pytest

from docparse.dataset.download import sha256_of
from docparse.dataset.manifest import Entry
from docparse.models import Registry
from docparse.parse import runner
from docparse.parse.executors import JobSpec, WorkerExecutor
from docparse.parse.format import Block, read_result, result_path, validate_tree
from docparse.parse.select import select_pages


def make_pdf(path: Path, pages: int = 4):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as doc:
        for i in range(pages):
            doc.new_page(width=200, height=200).insert_text((20, 50), f"page {i + 1}")
        doc.save(path)


def entry(doc_id, raw, pages=4, page_range="", with_hash=True):
    pdf = raw / doc_id / "document.pdf"
    make_pdf(pdf, pages)
    return Entry(id=doc_id, pages=str(pages), page_range=page_range, sha256=sha256_of(pdf) if with_hash else "")


# ---- page selection

def test_page_range_limits_pages(tmp_path):
    docs, skipped = select_pages([entry("a", tmp_path, page_range="2-4")], tmp_path)
    assert docs[0].pages == [2, 3, 4] and skipped == []


def test_missing_and_mismatching_files_are_skipped(tmp_path):
    good = entry("good", tmp_path)
    bad = entry("bad", tmp_path)
    bad.sha256 = "0" * 64
    missing = Entry(id="gone", pages="2")
    docs, skipped = select_pages([good, bad, missing], tmp_path)
    assert [d.doc_id for d in docs] == ["good"]
    assert any("bad" in s and "sha256" in s for s in skipped) and any("gone" in s and "missing" in s for s in skipped)


def test_only_and_limit(tmp_path):
    entries = [entry("a", tmp_path), entry("b", tmp_path), entry("c", tmp_path)]
    docs, _ = select_pages(entries, tmp_path, only={"b", "c"}, limit=5)
    assert [(d.doc_id, d.pages) for d in docs] == [("b", [1, 2, 3, 4]), ("c", [1])]
    _, skipped = select_pages(entries, tmp_path, only={"zzz"})
    assert any("zzz" in s for s in skipped)


# ---- runner with a fake executor

class FakeExecutor:
    instances: list = []

    def __init__(self, key, registry, fail_pages=(), ):
        self.key, self.fail_pages = key, set(fail_pages)
        self.started = self.closed = False
        self.calls = []
        FakeExecutor.instances.append(self)

    def start(self):
        self.started = True

    def process(self, spec, job):
        self.calls.append(spec.page)
        if spec.page in self.fail_pages:
            raise RuntimeError("boom")
        return [Block(type="text", label="text", bbox=[1, 1, 50, 20], engine=self.key, text=f"p{spec.page}")]

    def close(self):
        self.closed = True


@pytest.fixture
def setup(tmp_path):
    FakeExecutor.instances = []
    raw = tmp_path / "raw"
    docs, _ = select_pages([entry("a", raw), entry("b", raw, pages=2)], raw)
    return docs, Registry.load(None), tmp_path


def kw(tmp_path, factory):
    return dict(results_dir=tmp_path / "results", pages_dir=tmp_path / "pages", executor_factory=factory, log=lambda m: None)


def test_run_writes_results_and_page_images(setup):
    docs, reg, tmp = setup
    counts = runner.run_engine("ocr", docs, reg, **kw(tmp, FakeExecutor))
    assert (counts.done, counts.skipped, counts.errors) == (6, 0, 0)
    res = read_result(result_path("ocr", "b", 2, tmp / "results"))
    assert res.status == "ok" and res.blocks[0].text == "p2" and (res.width, res.height) == (417, 417)
    assert (tmp / "pages" / "a" / "0003.png").exists()
    count, errors = validate_tree(tmp / "results")
    assert count == 6 and errors == []


def test_second_run_skips_and_does_not_load_model(setup):
    docs, reg, tmp = setup
    runner.run_engine("ocr", docs, reg, **kw(tmp, FakeExecutor))
    FakeExecutor.instances.clear()
    counts = runner.run_engine("ocr", docs, reg, **kw(tmp, FakeExecutor))
    assert (counts.done, counts.skipped) == (0, 6)
    assert FakeExecutor.instances == []  # nothing to do, so no model was loaded


def test_force_recomputes(setup):
    docs, reg, tmp = setup
    runner.run_engine("ocr", docs, reg, **kw(tmp, FakeExecutor))
    counts = runner.run_engine("ocr", docs, reg, force=True, **kw(tmp, FakeExecutor))
    assert counts.done == 6 and counts.skipped == 0


def test_failing_page_is_recorded_and_retried(setup):
    docs, reg, tmp = setup
    flaky = lambda key, registry: FakeExecutor(key, registry, fail_pages={2})  # noqa: E731
    counts = runner.run_engine("ocr", docs, reg, **kw(tmp, flaky))
    assert (counts.done, counts.errors) == (4, 2)  # page 2 of both documents
    res = read_result(result_path("ocr", "a", 2, tmp / "results"))
    assert res.status == "error" and "boom" in res.error and res.blocks == []
    assert read_result(result_path("ocr", "a", 3, tmp / "results")).status == "ok"  # the run went on
    again = runner.run_engine("ocr", docs, reg, **kw(tmp, FakeExecutor))
    assert (again.done, again.skipped, again.errors) == (2, 4, 0)  # only the failed pages are retried
    assert read_result(result_path("ocr", "a", 2, tmp / "results")).status == "ok"


def test_engines_run_one_after_another(setup):
    docs, reg, tmp = setup
    events = []

    class Tracking(FakeExecutor):
        def start(self):
            events.append(("start", self.key))

        def close(self):
            events.append(("close", self.key))

    runner.run_all(["layout", "ocr"], docs, reg, **kw(tmp, Tracking))
    assert events == [("start", "layout"), ("close", "layout"), ("start", "ocr"), ("close", "ocr")]


# ---- worker process with timeout (fake factory, no GPU)

def slow_factory(registry):
    def work(spec: JobSpec):
        if spec.page == 2:
            time.sleep(60)
        if spec.page == 3:
            raise ValueError("bad page")
        return [Block(type="text", label="text", bbox=[0, 0, 1, 1], engine="vl", text=f"p{spec.page}")]
    return work


def test_worker_timeout_error_and_restart(tmp_path):
    ex = WorkerExecutor(Registry.load(None), timeout_s=3, factory=slow_factory, load_timeout_s=60)
    spec = lambda p: JobSpec("d", tmp_path / "x.pdf", p, 150)  # noqa: E731
    try:
        ex.start()
        assert ex.process(spec(1))[0].text == "p1"
        t0 = time.monotonic()
        with pytest.raises(RuntimeError, match="exceeded the limit of 3 s"):
            ex.process(spec(2))
        assert time.monotonic() - t0 < 20
        assert ex.process(spec(4))[0].text == "p4"  # a fresh worker takes over
        with pytest.raises(RuntimeError, match="bad page"):
            ex.process(spec(3))
        assert ex.process(spec(5))[0].text == "p5"
        assert ex.starts == 3
    finally:
        ex.close()


# ---- run_vl backend dispatch (MLX path calls handle.parse_page, CUDA path calls predict)

def test_run_vl_mlx_backend_uses_parse_page():
    """On the MLX backend run_vl must use handle.parse_page (layout+recognition composition), not the
    Paddle handle.predict page pipeline. Verifies the one backend-specific seam in the runner."""
    from docparse.parse.engines import PageJob, run_vl
    from docparse.parse.render import RenderedPage
    import numpy as np
    import pymupdf

    class FakeMlxVl:
        def parse_page(self, image):
            return [{"label": "text", "bbox": [0, 0, 10, 10], "content": "hi", "polygon_points": None}]

        def predict(self, *a, **k):  # must NOT be called on the mlx path
            raise AssertionError("predict() called on the MLX backend")

    rendered = RenderedPage(np.zeros((20, 20, 3), dtype=np.uint8), 20, 20, 150, pymupdf.Matrix(1, 1))
    job = PageJob("d", None, 1, rendered)
    blocks = run_vl(FakeMlxVl(), job, {"backend": "mlx", "max_new_tokens": 100})
    assert len(blocks) == 1 and blocks[0].engine == "vl" and blocks[0].text == "hi"
