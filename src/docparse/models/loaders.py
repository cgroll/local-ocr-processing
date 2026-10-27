"""One loader per component. Heavy imports happen inside `load` so the registry works without a GPU."""
from dataclasses import dataclass
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
        from .platform_setup import ensure_paddle_downloads
        ensure_paddle_downloads()
        from paddleocr import PaddleOCR
        return PaddleOCR(lang=spec.params["lang"], ocr_version=spec.params["ocr_version"])


class LayoutLoader(_Base):
    def load(self, spec: ModelSpec):
        from .platform_setup import ensure_paddle_downloads
        ensure_paddle_downloads()
        from paddleocr import LayoutDetection
        return LayoutDetection(model_name=spec.params["model_name"])


class VlLoader(_Base):
    def load(self, spec: ModelSpec):
        if spec.params.get("backend") == "mlx":
            # MLX path: PaddleOCR-VL has no page-level pipeline here, so pair it with a CPU
            # PP-DocLayout detector and compose per-region (see mlx_backends.MlxVlHandle).
            from .platform_setup import ensure_paddle_downloads
            ensure_paddle_downloads()
            from paddleocr import LayoutDetection

            from .mlx_backends import load_mlx_vl

            detector = LayoutDetection(model_name="PP-DocLayoutV3")
            return load_mlx_vl(spec.params["mlx_model_id"], detector, spec.params["max_new_tokens"])

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
        if spec.params.get("backend") == "mlx":
            from .mlx_backends import load_mlx_embedding
            return load_mlx_embedding(spec.params["mlx_model_id"], spec.params["dim"])

        import torch
        from sentence_transformers import SentenceTransformer

        config_kwargs = {} if spec.params["audio_encoder"] else {"audio_config": None}
        return SentenceTransformer(
            spec.params["model_id"], device="cuda", config_kwargs=config_kwargs,
            model_kwargs={"dtype": torch.bfloat16},
        )


@dataclass
class DescribeHandle:
    """Bundles the model and its processor; `describe()` is the one operation callers need."""
    model: Any
    processor: Any
    max_new_tokens: int

    def describe(self, image, prompt: str) -> str:
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image}, {"type": "text", "text": prompt},
        ]}]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=[image], return_tensors="pt").to(self.model.device)
        return self._generate(inputs, self.max_new_tokens)

    def generate_text(self, prompt: str, max_new_tokens: int | None = None) -> str:
        """Text-only call (no image) -- e.g. for summarizing an already-extracted document."""
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], return_tensors="pt").to(self.model.device)
        return self._generate(inputs, max_new_tokens or self.max_new_tokens)

    def _generate(self, inputs, max_new_tokens: int) -> str:
        import torch
        with torch.inference_mode():
            out_ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens)
        trimmed = out_ids[:, inputs["input_ids"].shape[1]:]
        return self.processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()


class DescribeLoader(_Base):
    def load(self, spec: ModelSpec):
        if spec.params.get("backend") == "mlx":
            from .mlx_backends import load_mlx_describe
            return load_mlx_describe(spec.params["mlx_model_id"], spec.params["max_new_tokens"])

        import torch
        from transformers import AutoProcessor, BitsAndBytesConfig, Qwen2_5_VLForConditionalGeneration

        quant_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            spec.params["model_id"], quantization_config=quant_config, device_map="cuda", dtype=torch.bfloat16,
        )
        processor = AutoProcessor.from_pretrained(spec.params["model_id"])
        return DescribeHandle(model, processor, spec.params["max_new_tokens"])

    def unload(self, handle: Any) -> None:
        del handle.model, handle.processor
        super().unload(handle)


def default_loaders() -> dict[str, _Base]:
    return {
        "pymupdf": PyMuPDFLoader(), "layout": LayoutLoader(), "ocr": OcrLoader(),
        "vl": VlLoader(), "embedding": EmbeddingLoader(), "describe": DescribeLoader(),
    }
