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


def manager(free_mb=lambda: 8000):
    loaders = {k: FakeLoader() for k in Registry.load(None).keys()}
    return ModelManager(Registry.load(None), loaders, free_mb), loaders


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
    with pytest.raises(ModelLoadError, match=r"'ocr'.*\['vl'\].*MB needed, 7680 MB usable"):
        m.load("ocr")
    assert m.loaded == ["vl"] and loaders["ocr"].loads == 0


def test_foreign_process_memory_is_reported():
    m, loaders = manager(free_mb=lambda: 3000)
    with pytest.raises(ModelLoadError, match="only 3000 MB free"):
        m.load("vl")
    assert loaders["vl"].loads == 0


def test_unknown_gpu_reading_does_not_block():
    m, _ = manager(free_mb=lambda: None)
    m.load("vl")


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
