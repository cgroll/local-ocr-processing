"""Render PDF pages once at a fixed DPI; all engines and all coordinates refer to this image."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pymupdf

DEFAULT_DPI = 150
PAGES_DIR = Path("data/pages")


@dataclass
class RenderedPage:
    image: np.ndarray  # BGR, as Paddle expects
    width: int
    height: int
    dpi: int
    to_pixels: pymupdf.Matrix  # maps PyMuPDF text/drawing coordinates (points) to image pixels


def page_image_path(doc_id: str, page: int, root: Path = PAGES_DIR) -> Path:
    return root / doc_id / f"{page:04d}.png"


def render_page(pdf_path: Path, page: int, dpi: int = DEFAULT_DPI, out_path: Path | None = None) -> RenderedPage:
    """Render 1-based `page` as displayed (rotation and crop box applied) and save the PNG if `out_path` is given."""
    with pymupdf.open(pdf_path) as doc:
        pg = doc[page - 1]
        scale = pymupdf.Matrix(dpi / 72, dpi / 72)
        pix = pg.get_pixmap(matrix=scale, colorspace=pymupdf.csRGB, alpha=False)
        to_pixels = pg.rotation_matrix * scale
        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(out_path)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return RenderedPage(np.ascontiguousarray(rgb[:, :, ::-1]), pix.width, pix.height, dpi, to_pixels)


def rect_to_pixels(rect, to_pixels: pymupdf.Matrix) -> list[float]:
    r = pymupdf.Rect(rect) * to_pixels
    r.normalize()
    return [r.x0, r.y0, r.x1, r.y1]
