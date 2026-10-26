from pathlib import Path

import numpy as np
from PIL import Image

from docparse.enrich.format import PageEnrichment, VisualBlock
from docparse.search.embed import embed_page


class FakeEmbeddingModel:
    """Returns a fixed-size vector whose first component tags what kind of input it saw, so
    tests can check the right object (and not e.g. an image where text was expected) was passed."""
    def encode(self, x, prompt_name=None):
        tag = 1.0 if isinstance(x, Image.Image) else (2.0 if prompt_name else 3.0)
        return np.array([tag, len(str(x)) if not isinstance(x, Image.Image) else x.size[0]], dtype=np.float32)


class FakeManager:
    def __init__(self):
        self.model = FakeEmbeddingModel()
        self.loaded = []

    def load(self, key):
        self.loaded.append(key)
        return self.model


def _png(path: Path, size=(20, 10)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)


def test_embed_page_covers_text_image_and_visual_blocks(tmp_path):
    page_png = tmp_path / "0001.png"
    _png(page_png)
    ok_crop = tmp_path / "table.png"
    _png(ok_crop, size=(40, 30))

    enrichment = PageEnrichment(
        "d", 1, "pymupdf", narrative_text="hello world",
        visual_blocks=[
            VisualBlock(type="table", label="table", bbox=[0, 0, 1, 1], position=0,
                        crop_path=str(ok_crop), description="a table", content_text="<table></table>"),
        ],
    )
    manager = FakeManager()
    items, vectors = embed_page(manager, enrichment, page_png)

    kinds = {(i.key.split("/")[-1], i.kind) for i in items}
    assert kinds == {
        ("PAGE_TEXT", "page_text"), ("PAGE_IMAGE", "page_image"),
        ("IMAGE", "visual_image"), ("DESC", "visual_desc"), ("CONTENT", "visual_content"),
    }
    assert vectors.shape == (5, 2)
    assert all(i.doc_id == "d" and i.page == 1 for i in items)
    assert [i.row for i in items] == list(range(5))
    assert manager.loaded == ["embedding"] * 5


def test_embed_page_skips_failed_blocks_and_missing_crops(tmp_path):
    page_png = tmp_path / "0001.png"
    _png(page_png)

    enrichment = PageEnrichment(
        "d", 1, "pymupdf", narrative_text="hello",
        visual_blocks=[
            VisualBlock(type="figure", label="image", bbox=[0, 0, 1, 1], position=0,
                        crop_path=str(tmp_path / "missing.png"), status="error", error="boom"),
        ],
    )
    items, vectors = embed_page(FakeManager(), enrichment, page_png)
    kinds = {i.kind for i in items}
    assert kinds == {"page_text", "page_image"}  # the failed block contributes nothing


def test_embed_page_without_narrative_text_or_page_image(tmp_path):
    enrichment = PageEnrichment("d", 1, "none", narrative_text="")
    items, vectors = embed_page(FakeManager(), enrichment, tmp_path / "missing.png")
    assert items == [] and vectors.shape == (0, 0)
