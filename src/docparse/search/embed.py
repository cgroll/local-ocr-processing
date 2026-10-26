"""Computes multimodal embeddings for one enriched page: page text, page image, and per
visual-block image/description/content, via the `embedding` model (EmbeddingGemma 2, already in
the model registry) -- text and images share one 768-dim space, see
experiments/multimodal-repr-test/README.md for the validation that this actually works (image
crop, topic-level description and full content land close together, correctly separated across
documents and block types)."""
from pathlib import Path

import numpy as np
from PIL import Image

from ..enrich.format import PageEnrichment
from ..models.lifecycle import ModelManager
from .format import EmbeddingItem

NARRATIVE_TEXT_CHAR_LIMIT = 8000  # EmbeddingGemma 2's 8192-token context is generous, but this
# keeps a single page's text comfortably inside it without a tokenizer round-trip here.
CONTENT_TEXT_CHAR_LIMIT = 4000


def _encode_text(manager: ModelManager, text: str) -> np.ndarray:
    model = manager.load("embedding")
    return np.asarray(model.encode(text, prompt_name="Document"))


def _encode_image(manager: ModelManager, image: Image.Image) -> np.ndarray:
    model = manager.load("embedding")
    return np.asarray(model.encode(image))


def embed_page(
    manager: ModelManager, enrichment: PageEnrichment, page_png: Path,
) -> tuple[list[EmbeddingItem], np.ndarray]:
    """Items + their vectors for one page: a page-text and page-image embedding when available,
    plus image/description/content embeddings for each successfully enriched visual block."""
    keys: list[str] = []
    kinds: list[str] = []
    vectors: list[np.ndarray] = []

    if enrichment.narrative_text.strip():
        keys.append("PAGE_TEXT")
        kinds.append("page_text")
        vectors.append(_encode_text(manager, enrichment.narrative_text[:NARRATIVE_TEXT_CHAR_LIMIT]))
    if page_png.exists():
        with Image.open(page_png) as img:
            keys.append("PAGE_IMAGE")
            kinds.append("page_image")
            vectors.append(_encode_image(manager, img.convert("RGB")))

    for vb in enrichment.visual_blocks:
        if vb.status != "ok":
            continue
        label = f"{vb.type}_{vb.position}"
        crop = Path(vb.crop_path)
        if crop.exists():
            with Image.open(crop) as img:
                keys.append(f"{label}/IMAGE")
                kinds.append("visual_image")
                vectors.append(_encode_image(manager, img.convert("RGB")))
        if vb.description:
            keys.append(f"{label}/DESC")
            kinds.append("visual_desc")
            vectors.append(_encode_text(manager, vb.description))
        if vb.content_text:
            keys.append(f"{label}/CONTENT")
            kinds.append("visual_content")
            vectors.append(_encode_text(manager, vb.content_text[:CONTENT_TEXT_CHAR_LIMIT]))

    if not vectors:
        return [], np.zeros((0, 0), dtype=np.float32)
    matrix = np.stack(vectors).astype(np.float32)
    items = [
        EmbeddingItem(f"{enrichment.doc_id}/{enrichment.page:04d}/{k}", enrichment.doc_id, enrichment.page, kind, row)
        for row, (k, kind) in enumerate(zip(keys, kinds))
    ]
    return items, matrix
