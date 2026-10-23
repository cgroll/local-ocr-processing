"""GPU memory readings via nvidia-smi (no extra dependency)."""
import gc
import subprocess
import sys
import threading
import time


def gpu_memory_mb() -> tuple[int, int] | None:
    """(used, total) of GPU 0 in MB, or None without a usable nvidia-smi."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
        used, total = out.splitlines()[0].split(",")
        return int(used), int(total)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def gpu_free_mb() -> int | None:
    mem = gpu_memory_mb()
    return None if mem is None else mem[1] - mem[0]


class PeakSampler:
    """Polls used GPU memory in a thread; `peak_mb` is the maximum seen while active."""

    def __init__(self, interval: float = 0.2):
        self.interval = interval
        self.peak_mb = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            mem = gpu_memory_mb()
            if mem:
                self.peak_mb = max(self.peak_mb, mem[0])
            time.sleep(self.interval)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()


def free_gpu_memory() -> None:
    """Collect garbage and return cached blocks of the frameworks that are loaded to the driver."""
    gc.collect()
    if "paddle" in sys.modules:
        sys.modules["paddle"].device.cuda.empty_cache()
    if "torch" in sys.modules:
        sys.modules["torch"].cuda.empty_cache()
