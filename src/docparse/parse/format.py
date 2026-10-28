"""Per-page intermediate format: blocks in pixel coordinates of the rendered page image."""
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

VERSION = 1
RESULTS_DIR = Path("data/results")

BLOCK_TYPES = (
    "text", "title", "header", "footer", "table", "figure", "formula", "chart",
    "list", "caption", "line", "cell", "image", "drawing", "other",
)
STATUSES = ("ok", "error")
BOX_TOLERANCE_PX = 2.0


@dataclass
class Block:
    type: str
    label: str  # the engine's own name for the block
    bbox: list[float]  # [x0, y0, x1, y1] pixels, origin top left
    engine: str
    order: int | None = None
    confidence: float | None = None  # None when the engine gives none
    polygon: list[list[float]] | None = None
    text: str | None = None
    markdown: str | None = None
    html: str | None = None


@dataclass
class PageResult:
    doc_id: str
    page: int  # 1-based
    dpi: int
    width: int
    height: int
    engine: str
    engine_version: str = ""
    status: str = "ok"
    error: str | None = None
    seconds: float = 0.0
    blocks: list[Block] = field(default_factory=list)
    version: int = VERSION

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PageResult":
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in d.items() if k in known}
        data["blocks"] = [Block(**b) for b in d.get("blocks", [])]
        return cls(**data)


def result_path(engine: str, doc_id: str, page: int, root: Path = RESULTS_DIR) -> Path:
    return root / engine / doc_id / f"{page:04d}.json"


def write_result(result: PageResult, root: Path = RESULTS_DIR) -> Path:
    path = result_path(result.engine, result.doc_id, result.page, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def read_result(path: Path) -> PageResult:
    return PageResult.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def validate_result(result: PageResult) -> list[str]:
    """Problems found in one result; empty when it is valid."""
    errors = []
    if result.status not in STATUSES:
        errors.append(f"unknown status '{result.status}'")
    if result.status == "error" and not result.error:
        errors.append("status error without message")
    if result.width <= 0 or result.height <= 0 or result.dpi <= 0 or result.page < 1:
        errors.append("width, height, dpi and page must be positive")
    for i, b in enumerate(result.blocks):
        where = f"block {i}"
        if b.type not in BLOCK_TYPES:
            errors.append(f"{where}: unknown type '{b.type}'")
        if len(b.bbox) != 4:
            errors.append(f"{where}: bbox needs 4 values")
            continue
        x0, y0, x1, y1 = b.bbox
        if x0 > x1 or y0 > y1:
            errors.append(f"{where}: malformed bbox {b.bbox}")
        tol = BOX_TOLERANCE_PX
        if x0 < -tol or y0 < -tol or x1 > result.width + tol or y1 > result.height + tol:
            errors.append(f"{where}: bbox {b.bbox} outside image {result.width}x{result.height}")
        if b.engine != result.engine:
            errors.append(f"{where}: engine '{b.engine}' differs from result engine '{result.engine}'")
    return errors


def validate_tree(root: Path = RESULTS_DIR, engines: list[str] | None = None) -> tuple[int, list[str]]:
    """Validate every result file under root; returns (files checked, errors with file names)."""
    errors, count = [], 0
    for path in sorted(root.glob("*/*/*.json")):
        if engines and path.parts[-3] not in engines:
            continue
        count += 1
        try:
            result = read_result(path)
        except (OSError, ValueError, TypeError, KeyError) as e:
            errors.append(f"{path}: unreadable ({e})")
            continue
        errors += [f"{path}: {e}" for e in validate_result(result)]
    return count, errors
