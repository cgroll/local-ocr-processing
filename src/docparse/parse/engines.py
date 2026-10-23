"""Engine calls: run one loaded model on a rendered page and return blocks in the common format."""
from dataclasses import dataclass
from pathlib import Path

from .adapters import layout, ocr, pymupdf as pymupdf_adapter, vl
from .format import Block
from .render import RenderedPage

# Orientation correction and unwarping would change the image, so boxes would no longer match the page image.
NO_PREPROCESSING = {"use_doc_orientation_classify": False, "use_doc_unwarping": False}


@dataclass
class PageJob:
    doc_id: str
    pdf_path: Path
    page: int  # 1-based
    rendered: RenderedPage


def engine_version(key: str, name: str) -> str:
    if key == "pymupdf":
        import pymupdf
        return pymupdf.__version__
    if key == "embedding":
        return name
    import paddleocr
    return f"{name} (paddleocr {paddleocr.__version__})"


def run_pymupdf(handle, job: PageJob, params: dict) -> list[Block]:
    with handle.open(job.pdf_path) as doc:
        return pymupdf_adapter.to_blocks(doc[job.page - 1], job.rendered.to_pixels)


def run_layout(handle, job: PageJob, params: dict) -> list[Block]:
    return layout.to_blocks(handle.predict(job.rendered.image)[0]["boxes"])


def run_ocr(handle, job: PageJob, params: dict) -> list[Block]:
    res = handle.predict(job.rendered.image, **NO_PREPROCESSING)[0]
    return ocr.to_blocks({k: res[k] for k in ("rec_texts", "rec_scores", "rec_polys", "rec_boxes")})


def run_vl(handle, job: PageJob, params: dict) -> list[Block]:
    res = list(handle.predict(job.rendered.image, max_new_tokens=params["max_new_tokens"], **NO_PREPROCESSING))[0]
    raw = [
        {"label": b.label, "bbox": b.bbox, "content": b.content, "polygon_points": b.polygon_points}
        for b in res["parsing_res_list"]
    ]
    return vl.to_blocks(raw)


RUNNERS = {"pymupdf": run_pymupdf, "layout": run_layout, "ocr": run_ocr, "vl": run_vl}
