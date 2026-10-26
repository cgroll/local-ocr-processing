"""Per-page enrichment result: chosen text source, narrative text and enriched visual blocks
(crops + descriptions), written next to the engine results under `data/results/enrich/<doc>/`."""
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from ..parse.format import RESULTS_DIR

VERSION = 1
ENRICH_SUBDIR = "enrich"
STATUSES = ("ok", "error")


@dataclass
class VisualBlock:
    type: str  # "figure" | "chart" | "table"
    label: str
    bbox: list[float]
    position: int
    crop_path: str  # relative to the repo root
    status: str = "ok"
    error: str | None = None
    description: str | None = None
    content_text: str | None = None  # tables only
    content_source: str | None = None  # "vl" | "pymupdf" | None


@dataclass
class PageEnrichment:
    doc_id: str
    page: int  # 1-based
    text_source: str  # "pymupdf" | "ocr" | "none"
    narrative_text: str = ""
    visual_blocks: list[VisualBlock] = field(default_factory=list)
    status: str = "ok"
    error: str | None = None
    seconds: float = 0.0
    version: int = VERSION

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PageEnrichment":
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in d.items() if k in known}
        data["visual_blocks"] = [VisualBlock(**b) for b in d.get("visual_blocks", [])]
        return cls(**data)


def enrich_dir(doc_id: str, root: Path = RESULTS_DIR) -> Path:
    return root / ENRICH_SUBDIR / doc_id


def result_path(doc_id: str, page: int, root: Path = RESULTS_DIR) -> Path:
    return enrich_dir(doc_id, root) / f"{page:04d}.json"


def crop_path(doc_id: str, page: int, block_type: str, position: int, root: Path = RESULTS_DIR) -> Path:
    return enrich_dir(doc_id, root) / f"{page:04d}_{block_type}_{position}.png"


def write_result(result: PageEnrichment, root: Path = RESULTS_DIR) -> Path:
    path = result_path(result.doc_id, result.page, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def read_result(path: Path) -> PageEnrichment:
    return PageEnrichment.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
