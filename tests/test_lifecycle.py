from dataclasses import replace

import pytest

from docparse.models import Registry
from docparse.models.lifecycle import ModelLoadError, ModelManager


class FakeLoader:
    def __init__(self):
        self.loads = 0
        self.unloads = 0

    def load(self, spec):
        self.loads += 1
        return object()

    def unload(self, handle):
        self.unloads += 1


def _gpu_registry():
    """Registry with the accelerated models pinned to CUDA 'gpu', so the real-memory guard applies
    regardless of the host platform (on Apple Silicon the defaults would be 'mlx')."""
    base = Registry.load(None)
    specs = {k: replace(s, device="gpu" if s.device in {"gpu", "mlx"} else s.device) for k, s in base._specs.items()}
    return Registry(specs, base.budget)


def manager(free_mb=lambda: 8000, registry=None):
    registry = registry or _gpu_registry()
    loaders = {k: FakeLoader() for k in registry.keys()}
    return ModelManager(registry, loaders, free_mb), loaders


def test_load_unload_cycle():
    m, loaders = manager()
    m.load("ocr")
    assert m.loaded == ["ocr"]
    m.unload("ocr")
    assert m.loaded == [] and loaders["ocr"].unloads == 1


def test_second_load_reuses_instance():
    m, loaders = manager()
    assert m.load("ocr") is m.load("ocr")
    assert loaders["ocr"].loads == 1


def test_incompatible_combination_is_refused_and_keeps_loaded_model():
    m, loaders = manager()
    m.load("vl")
    m.load("ocr")
    with pytest.raises(ModelLoadError, match=r"'embedding'.*\['vl', 'ocr'\].*MB needed, 7680 MB usable"):
        m.load("embedding")
    assert m.loaded == ["vl", "ocr"] and loaders["embedding"].loads == 0


def test_foreign_process_memory_is_reported():
    m, loaders = manager(free_mb=lambda: 3000)
    with pytest.raises(ModelLoadError, match="only 3000 MB free"):
        m.load("vl")
    assert loaders["vl"].loads == 0


def test_unknown_gpu_reading_does_not_block():
    m, _ = manager(free_mb=lambda: None)
    m.load("vl")


def test_mlx_device_skips_real_memory_check():
    """On Apple Silicon (device 'mlx') there is no dedicated-VRAM reading; the real-memory guard is
    skipped and loading is allowed as long as the budget fits, even if free_mb reports a low value."""
    base = Registry.load(None)
    specs = {k: replace(s, device="mlx" if s.device in {"gpu", "mlx"} else s.device) for k, s in base._specs.items()}
    reg = Registry(specs, base.budget)
    called = []
    m, loaders = manager(free_mb=lambda: called.append(True) or 10, registry=reg)
    m.load("vl")  # vl needs 5500 MB; free_mb would say 10, but mlx skips that check
    assert loaders["vl"].loads == 1
    assert called == []  # the real-memory reader was never consulted for an mlx device


def test_mlx_device_still_honours_budget():
    """The budget-based fit check stays active for mlx devices (only the real reading is skipped)."""
    base = Registry.load(None)
    specs = {k: replace(s, device="mlx" if s.device in {"gpu", "mlx"} else s.device) for k, s in base._specs.items()}
    m, loaders = manager(registry=Registry(specs, base.budget))
    m.load("vl")
    with pytest.raises(ModelLoadError, match="MB needed, 7680 MB usable"):
        m.load("describe")  # vl (5500) + describe (3500) exceed the 7680 MB budget


def test_context_unloads_on_exception():
    m, loaders = manager()
    with pytest.raises(RuntimeError, match="boom"):
        with m.use("ocr"):
            raise RuntimeError("boom")
    assert m.loaded == [] and loaders["ocr"].unloads == 1


def test_unload_all_in_reverse_order():
    m, loaders = manager()
    m.load("layout")
    m.load("ocr")
    m.unload_all()
    assert m.loaded == [] and loaders["layout"].unloads == loaders["ocr"].unloads == 1
