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
    """Collect garbage and return cached blocks of the frameworks that are loaded to the driver.

    CUDA cache clearing is a no-op (and errors on some builds) without a CUDA device -- e.g. the
    CPU paddlepaddle / MLX stack on Apple Silicon -- so each call is guarded by a compiled-with-CUDA
    check. MLX frees its own buffers once the handle's references are dropped; gc.collect() is enough.
    """
    gc.collect()
    paddle = sys.modules.get("paddle")
    if paddle is not None:
        try:
            if paddle.device.is_compiled_with_cuda():
                paddle.device.cuda.empty_cache()
        except Exception:
            pass
    torch = sys.modules.get("torch")
    if torch is not None:
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
