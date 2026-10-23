"""One loader per component. Heavy imports happen inside `load` so the registry works without a GPU."""
from typing import Any

from .registry import ModelSpec


class _Base:
    def unload(self, handle: Any) -> None:
        # The manager frees GPU caches after it dropped its own reference.
        close = getattr(handle, "close", None)
        if callable(close):
            close()


class PyMuPDFLoader(_Base):
    def load(self, spec: ModelSpec):
        import pymupdf
        return pymupdf


class OcrLoader(_Base):
    def load(self, spec: ModelSpec):
        from paddleocr import PaddleOCR
        return PaddleOCR(lang=spec.params["lang"], ocr_version=spec.params["ocr_version"])


class LayoutLoader(_Base):
    def load(self, spec: ModelSpec):
        from paddleocr import LayoutDetection
        return LayoutDetection(model_name=spec.params["model_name"])


class VlLoader(_Base):
    def load(self, spec: ModelSpec):
        from paddleocr import PaddleOCRVL

        if spec.params["vision_bf16"]:
            # Keep the vision encoder in bf16 too (default fp32): without the headroom, long generations
            # on an 8 GB card thrash the allocator or run out of memory and take minutes per page.
            from paddlex.inference.models.doc_vlm.modeling.paddleocr_vl._paddleocr_vl import (
                PaddleOCRVLForConditionalGeneration,
            )
            PaddleOCRVLForConditionalGeneration._keep_in_fp32_modules = None
        return PaddleOCRVL(markdown_ignore_labels=spec.params["markdown_ignore_labels"])


class EmbeddingLoader(_Base):
    def load(self, spec: ModelSpec):
        import torch
        from sentence_transformers import SentenceTransformer

        config_kwargs = {} if spec.params["audio_encoder"] else {"audio_config": None}
        return SentenceTransformer(
            spec.params["model_id"], device="cuda", config_kwargs=config_kwargs,
            model_kwargs={"dtype": torch.bfloat16},
        )


def default_loaders() -> dict[str, _Base]:
    return {
        "pymupdf": PyMuPDFLoader(), "layout": LayoutLoader(), "ocr": OcrLoader(),
        "vl": VlLoader(), "embedding": EmbeddingLoader(),
    }
