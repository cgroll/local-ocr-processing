"""Sequential model loading under a VRAM budget."""
from contextlib import contextmanager
from typing import Any, Callable, Protocol

from .gpu import free_gpu_memory, gpu_free_mb
from .registry import ModelSpec, Registry


class ModelLoadError(RuntimeError):
    pass


class Loader(Protocol):
    def load(self, spec: ModelSpec) -> Any: ...
    def unload(self, handle: Any) -> None: ...


class ModelManager:
    def __init__(
        self,
        registry: Registry,
        loaders: dict[str, Loader] | None = None,
        free_mb: Callable[[], int | None] = gpu_free_mb,
    ):
        if loaders is None:
            from .loaders import default_loaders
            loaders = default_loaders()
        self.registry = registry
        self._loaders = loaders
        self._free_mb = free_mb
        self._loaded: dict[str, Any] = {}

    @property
    def loaded(self) -> list[str]:
        return list(self._loaded)

    def check(self, key: str) -> None:
        """Raise ModelLoadError unless `key` fits next to the loaded models and the real free VRAM."""
        spec = self.registry.get(key)
        fit = self.registry.fits([*self._loaded, key])
        if not fit.ok:
            raise ModelLoadError(
                f"cannot load '{key}' ({spec.vram_mb} MB) while {self.loaded or 'nothing'} is loaded: {fit}"
            )
        if spec.device == "gpu" and spec.vram_mb:
            free = self._free_mb()
            if free is not None and free < spec.vram_mb:
                raise ModelLoadError(
                    f"cannot load '{key}': needs {spec.vram_mb} MB but the GPU reports only {free} MB free "
                    f"(loaded here: {self.loaded or 'none'}; other processes may hold memory)"
                )

    def load(self, key: str) -> Any:
        if key in self._loaded:
            return self._loaded[key]
        self.check(key)
        handle = self._loaders[key].load(self.registry.get(key))
        self._loaded[key] = handle
        return handle

    def unload(self, key: str) -> None:
        handle = self._loaded.pop(key, None)
        if handle is not None:
            self._loaders[key].unload(handle)
            del handle  # no reference may survive, or the caches below cannot release the memory
            free_gpu_memory()

    def unload_all(self) -> None:
        for key in reversed(self.loaded):
            self.unload(key)

    @contextmanager
    def use(self, key: str):
        handle = self.load(key)
        try:
            yield handle
        finally:
            self.unload(key)
