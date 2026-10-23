"""Model registry: the single source for which models exist, their pins and VRAM cost."""
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path("models.toml")
DEFAULT_TOTAL_MB = 8192
DEFAULT_RESERVE_MB = 512


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ModelSpec:
    key: str
    task: str
    name: str  # model name or version pin
    device: str  # "cpu" or "gpu"
    vram_mb: int  # estimate; measured by `python -m docparse.models smoke`
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Budget:
    total_mb: int = DEFAULT_TOTAL_MB
    reserve_mb: int = DEFAULT_RESERVE_MB

    @property
    def usable_mb(self) -> int:
        return self.total_mb - self.reserve_mb


@dataclass(frozen=True)
class Fit:
    ok: bool
    needed_mb: int
    budget_mb: int

    def __str__(self) -> str:
        verdict = "fits" if self.ok else "does not fit"
        return f"{self.needed_mb} MB needed, {self.budget_mb} MB usable: {verdict}"


def default_specs() -> dict[str, ModelSpec]:
    specs = [
        ModelSpec("pymupdf", "native text layer, images, vector graphics", "pymupdf", "cpu", 0),
        ModelSpec(
            "layout", "layout blocks with type, box and reading order", "PP-DocLayoutV3", "gpu", 750,
            {"model_name": "PP-DocLayoutV3"},
        ),
        ModelSpec(
            "ocr", "text line detection and recognition", "PP-OCRv6", "gpu", 1450,
            {"lang": "de", "ocr_version": "PP-OCRv6"},
        ),
        # Includes its own PP-DocLayoutV3 instance, so `vl` and `layout` are not loaded together.
        ModelSpec(
            "vl", "tables, formulas and charts as markdown/html", "PaddleOCR-VL-1.6", "gpu", 7600,
            {"max_new_tokens": 4096, "timeout_s": 180, "markdown_ignore_labels": []},
        ),
        ModelSpec(
            "embedding", "text and image embeddings in one 768-dim space", "google/embeddinggemma-2", "gpu", 1100,
            {"model_id": "google/embeddinggemma-2", "dim": 768, "audio_encoder": False},
        ),
    ]
    return {s.key: s for s in specs}


class Registry:
    def __init__(self, specs: dict[str, ModelSpec], budget: Budget | None = None):
        self._specs = specs
        self.budget = budget or Budget()

    @classmethod
    def load(cls, config: Path | None = DEFAULT_CONFIG) -> "Registry":
        """Defaults plus overrides from `config`; a missing file means no overrides."""
        specs = default_specs()
        budget = Budget()
        if config is not None and Path(config).exists():
            raw = tomllib.loads(Path(config).read_text())
            budget = _apply_budget(raw.get("budget", {}), budget, config)
            for key, override in raw.get("models", {}).items():
                if key not in specs:
                    raise RegistryError(f"{config}: unknown model '{key}', valid keys: {', '.join(specs)}")
                specs[key] = _apply_override(specs[key], override, config)
        return cls(specs, budget)

    def keys(self) -> list[str]:
        return list(self._specs)

    def get(self, key: str) -> ModelSpec:
        try:
            return self._specs[key]
        except KeyError:
            raise RegistryError(f"unknown model '{key}', valid keys: {', '.join(self._specs)}") from None

    def specs(self) -> list[ModelSpec]:
        return list(self._specs.values())

    def with_vram(self, key: str, vram_mb: int) -> "Registry":
        return Registry({**self._specs, key: replace(self.get(key), vram_mb=vram_mb)}, self.budget)

    def fits(self, keys: list[str]) -> Fit:
        needed = sum(self.get(k).vram_mb for k in set(keys))
        return Fit(needed <= self.budget.usable_mb, needed, self.budget.usable_mb)


def _apply_budget(raw: dict, budget: Budget, config) -> Budget:
    unknown = set(raw) - {"total_mb", "reserve_mb"}
    if unknown:
        raise RegistryError(f"{config}: unknown budget field '{sorted(unknown)[0]}'")
    return replace(budget, **raw)


def _apply_override(spec: ModelSpec, override: dict, config) -> ModelSpec:
    unknown_sections = set(override) - {"params"}
    if unknown_sections:
        raise RegistryError(f"{config}: [{spec.key}] only 'params' can be overridden, got '{sorted(unknown_sections)[0]}'")
    params = dict(spec.params)
    for name, value in override.get("params", {}).items():
        if name not in params:
            raise RegistryError(
                f"{config}: unknown parameter '{name}' for model '{spec.key}', valid: {', '.join(params) or 'none'}"
            )
        params[name] = value
    return replace(spec, params=params)
