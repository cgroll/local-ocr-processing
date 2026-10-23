"""How a page is processed by one engine: in this process, or in a killable worker process (VL)."""
import multiprocessing as mp
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..models import Registry
from ..models.lifecycle import ModelManager
from .engines import RUNNERS, PageJob
from .format import Block
from .render import render_page

LOAD_TIMEOUT_S = 900  # first start may download weights


class PageTimeout(RuntimeError):
    pass


@dataclass(frozen=True)
class JobSpec:
    doc_id: str
    pdf_path: Path
    page: int
    dpi: int


def make_job(spec: JobSpec) -> PageJob:
    return PageJob(spec.doc_id, spec.pdf_path, spec.page, render_page(spec.pdf_path, spec.page, spec.dpi))


class InProcessExecutor:
    """Loads the model once via the ModelManager; pages run in this process."""

    def __init__(self, key: str, registry: Registry):
        self.key, self.registry = key, registry
        self.manager = ModelManager(registry)
        self.handle = None

    def start(self) -> None:
        self.handle = self.manager.load(self.key)

    def process(self, spec: JobSpec, job: PageJob) -> list[Block]:
        return RUNNERS[self.key](self.handle, job, self.registry.get(self.key).params)

    def close(self) -> None:
        self.handle = None
        self.manager.unload_all()


def _vl_factory(registry: Registry) -> Callable[[JobSpec], list[Block]]:
    manager = ModelManager(registry)
    handle = manager.load("vl")
    params = registry.get("vl").params

    def work(spec: JobSpec) -> list[Block]:
        return RUNNERS["vl"](handle, make_job(spec), params)
    return work


def _worker_main(conn, registry: Registry, factory) -> None:
    try:
        work = factory(registry)
        conn.send(("ready",))
        while True:
            spec = conn.recv()
            if spec is None:
                break
            try:
                conn.send(("ok", work(spec)))
            except Exception as e:  # the parent restarts the worker after any error
                conn.send(("error", f"{type(e).__name__}: {e}"))
    except Exception as e:
        conn.send(("error", f"worker failed to start: {type(e).__name__}: {e}"))
    finally:
        conn.close()


class WorkerExecutor:
    """Runs pages in a spawned process so a stuck generation can be killed and its VRAM is freed on exit.

    A page that exceeds `timeout_s`, or any error inside the worker, ends the worker; the next page
    starts a fresh one.
    """

    def __init__(self, registry: Registry, timeout_s: float, factory=_vl_factory, load_timeout_s: float = LOAD_TIMEOUT_S):
        self.registry, self.timeout_s, self.factory, self.load_timeout_s = registry, timeout_s, factory, load_timeout_s
        self._proc = None
        self._conn = None
        self.starts = 0

    def _start(self) -> None:
        ctx = mp.get_context("spawn")
        parent, child = ctx.Pipe(duplex=True)
        self._proc = ctx.Process(target=_worker_main, args=(child, self.registry, self.factory), daemon=True)
        self._proc.start()
        child.close()
        self._conn = parent
        self.starts += 1
        msg = self._wait(self.load_timeout_s, "loading")
        if msg[0] != "ready":
            self._stop()
            raise RuntimeError(msg[1])

    def _wait(self, timeout: float, what: str):
        if not self._conn.poll(timeout):
            self._stop()
            raise PageTimeout(f"{what} exceeded the limit of {timeout:g} s")
        try:
            return self._conn.recv()
        except EOFError:
            self._stop()
            raise RuntimeError("worker process died without a result") from None

    def _stop(self) -> None:
        if self._proc is not None:
            if self._proc.is_alive():
                self._proc.kill()
            self._proc.join()
        if self._conn is not None:
            self._conn.close()
        self._proc = self._conn = None

    def start(self) -> None:
        if self._proc is None:
            self._start()

    def process(self, spec: JobSpec, job: PageJob | None = None) -> list[Block]:
        if self._proc is None:
            self._start()
        self._conn.send(spec)
        msg = self._wait(self.timeout_s, "inference")
        if msg[0] == "ok":
            return msg[1]
        self._stop()
        raise RuntimeError(msg[1])

    def close(self) -> None:
        if self._proc is not None and self._proc.is_alive():
            try:
                self._conn.send(None)
                self._proc.join(10)
            except OSError:
                pass
        self._stop()
