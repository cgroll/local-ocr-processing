"""Apple Silicon (MLX) backends for the models that have no CUDA path on macOS.

Why this module exists: `paddlepaddle-gpu`, `bitsandbytes` 4-bit and CUDA `SentenceTransformer`
have no macOS wheels or no Metal backend. On Apple Silicon the same three models run through
`mlx-vlm` on the M-series GPU instead. The reference implementation this follows is `~/repos/EEP`
(`eep/vlm.py`, `eep/embed.py`). Each handle below mirrors the exact call surface the CUDA handle
exposes, so the rest of the pipeline (search/embed.py, enrich/describe.py, parse/engines.py) is
unchanged.

Heavy imports (`mlx_vlm`, `mlx.core`) happen lazily inside methods/constructors so the registry and
non-MLX code paths keep working without MLX installed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

# Where locally-downloaded MLX weights live. The HF Xet CDN is blocked behind some corporate
# proxies (Zscaler), so weights are fetched from ModelScope into this dir (see scripts/get_models.py)
# and loaded from disk. Override with DOCPARSE_MLX_MODELS_DIR. Falls back to the HF repo id when a
# matching local dir is absent (works on an unproxied network).
_MODELS_DIR = Path(os.environ.get("DOCPARSE_MLX_MODELS_DIR", "models"))


def resolve_model(mlx_model_id: str) -> str:
    """A local `models/<basename>` dir if present, otherwise the HF repo id itself."""
    local = _MODELS_DIR / mlx_model_id.split("/")[-1]
    return str(local) if (local / "config.json").exists() else mlx_model_id

# EmbeddingGemma 2 task-instruction prefixes (from the model card; same as ~/repos/EEP/eep/embed.py).
# The CUDA SentenceTransformer applies these via prompt_name; here we prepend them ourselves.
_EMBED_PROMPTS: dict[str, str] = {
    "SearchQuery": "task: search result | query: ",
    "Document": "title: none | text: ",
    "QuestionAnswering": "task: question answering | query: ",
    "Classification": "task: classification | query: ",
    "Clustering": "task: clustering | query: ",
    "SentenceSimilarity": "task: sentence similarity | query: ",
}


@dataclass
class MlxEmbeddingHandle:
    """Mirrors the `SentenceTransformer` call surface the search code uses: `encode(text_or_image,
    prompt_name=...)` returning an L2-normalised float32 vector in the shared 768-dim space."""

    model: Any
    processor: Any
    dim: int

    def encode(self, data, prompt_name: str | None = "Document", **_ignored):
        """Encode one text string or one PIL image. Returns a 1-D float32 numpy array (L2-normed)."""
        if isinstance(data, str):
            return self._encode_text(data, prompt_name)
        return self._encode_image(data)

    # -- internals ---------------------------------------------------------
    def _finalize(self, emb) -> np.ndarray:
        import mlx.core as mx

        if self.dim and emb.shape[-1] > self.dim:
            emb = emb[:, : self.dim]
            emb = emb / mx.linalg.norm(emb, axis=-1, keepdims=True)  # slicing breaks unit norm
        mx.eval(emb)
        vec = np.asarray(emb)[0].astype(np.float32)
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    def _encode_text(self, text: str, prompt_name: str | None) -> np.ndarray:
        import mlx.core as mx

        prefix = _EMBED_PROMPTS.get(prompt_name, "") if prompt_name else ""
        inp = self.processor.tokenizer([prefix + text], padding=True, return_tensors="np")
        out = self.model(**{k: mx.array(v) for k, v in inp.items()}).text_embeds
        return self._finalize(out)

    def _encode_image(self, image) -> np.ndarray:
        import io
        import tempfile

        # mlx-vlm's chat template takes an image URL/path; write the PIL image to a temp file.
        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
            image.save(tmp.name, format="PNG")
            conv = [[{"role": "user", "content": [{"type": "image", "url": tmp.name}]}]]
            inputs = self.processor.apply_chat_template(
                conv, tokenize=True, return_dict=True, return_tensors="mlx", max_soft_tokens=280,
            )
            out = self.model(**inputs).text_embeds
        return self._finalize(out)


def load_mlx_embedding(model_id: str, dim: int) -> MlxEmbeddingHandle:
    from mlx_vlm import load

    model, processor = load(resolve_model(model_id))
    return MlxEmbeddingHandle(model, processor, dim)


# -- PaddleOCR-VL recognition (element-wise) -------------------------------

# PP-DocLayout label -> PaddleOCR-VL task prompt (same mapping as ~/repos/EEP/eep/config.py).
_VL_TASK_PROMPTS: dict[str, str] = {
    "table": "Table Recognition:",
    "chart": "Chart Recognition:",
    "formula": "Formula Recognition:",
    "inline_formula": "Formula Recognition:",
}
_VL_DEFAULT_PROMPT = "OCR:"


def vl_prompt_for_label(label: str) -> str:
    return _VL_TASK_PROMPTS.get(label, _VL_DEFAULT_PROMPT)


@dataclass
class MlxVlHandle:
    """PaddleOCR-VL via mlx-vlm with the layout-plus-recognition composition the MLX path needs.

    The CUDA Paddle pipeline returns a whole-page `parsing_res_list`; mlx-vlm has no such page-level
    pipeline, so here a layout detector (PP-DocLayout on CPU paddle) supplies the regions and each is
    recognised with a task-specific prompt. `parse_page()` returns the same list of raw block dicts
    (`label`, `bbox`, `content`, `polygon_points`, in reading order) that parse/adapters/vl.py
    already consumes -- so the downstream block format is identical across backends.
    """

    model: Any
    processor: Any
    layout_detector: Any  # paddleocr.LayoutDetection (CPU)
    max_new_tokens: int

    def recognise(self, image_path: str, prompt: str, *, max_tokens: int | None = None) -> str:
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        formatted = apply_chat_template(self.processor, self.model.config, prompt, num_images=1)
        res = generate(
            model=self.model,
            processor=self.processor,
            prompt=formatted,
            image=[str(image_path)],
            max_tokens=max_tokens or self.max_new_tokens,
            temperature=0.0,  # greedy: parsing is deterministic work
            verbose=False,
        )
        return (res.text or "").strip()

    def parse_page(self, image_bgr) -> list[dict]:
        """Detect regions, recognise each, and return raw VL block dicts in reading order.

        `image_bgr` is the BGR numpy page image (as the Paddle engines receive it). Table output is
        PaddleOCR-VL's OTSL token stream, which `run_vl` turns into HTML via parse/otsl.py (the
        adapter keys HTML off a `<table` marker, same as the CUDA path)."""
        import tempfile

        from PIL import Image

        from ..parse.otsl import looks_like_otsl, otsl_to_html

        boxes = self.layout_detector.predict(image_bgr)[0]["boxes"]
        # Reading order: top-to-bottom, then left-to-right (the detector's own order is not reliable).
        boxes = sorted(boxes, key=lambda b: (round(float(b["coordinate"][1]) / 10), float(b["coordinate"][0])))
        rgb = Image.fromarray(image_bgr[:, :, ::-1])  # BGR -> RGB
        raw: list[dict] = []
        for b in boxes:
            label = str(b.get("label", "text"))
            x1, y1, x2, y2 = (float(v) for v in b["coordinate"][:4])
            with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
                rgb.crop((int(x1), int(y1), int(x2), int(y2))).save(tmp.name, format="PNG")
                content = self.recognise(tmp.name, vl_prompt_for_label(label))
            if looks_like_otsl(content):
                content = otsl_to_html(content)  # -> HTML, which the adapter treats as a table block
            raw.append({
                "label": label,
                "bbox": [x1, y1, x2, y2],
                "content": content,
                "polygon_points": b.get("polygon_points"),
            })
        return raw


def load_mlx_vl(model_id: str, layout_detector: Any, max_new_tokens: int) -> MlxVlHandle:
    from mlx_vlm import load

    model, processor = load(resolve_model(model_id))
    return MlxVlHandle(model, processor, layout_detector, max_new_tokens)


# -- describe (Qwen2.5-VL via MLX) -----------------------------------------


@dataclass
class MlxDescribeHandle:
    """Mirrors loaders.DescribeHandle: `describe(image, prompt)` and `generate_text(prompt)`."""

    model: Any
    processor: Any
    max_new_tokens: int

    def describe(self, image, prompt: str) -> str:
        import tempfile

        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
            image.save(tmp.name, format="PNG")
            formatted = apply_chat_template(self.processor, self.model.config, prompt, num_images=1)
            res = generate(
                model=self.model, processor=self.processor, prompt=formatted,
                image=[tmp.name], max_tokens=self.max_new_tokens, temperature=0.0, verbose=False,
            )
        return (res.text or "").strip()

    def generate_text(self, prompt: str, max_new_tokens: int | None = None) -> str:
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        formatted = apply_chat_template(self.processor, self.model.config, prompt, num_images=0)
        res = generate(
            model=self.model, processor=self.processor, prompt=formatted,
            max_tokens=max_new_tokens or self.max_new_tokens, temperature=0.0, verbose=False,
        )
        return (res.text or "").strip()


def load_mlx_describe(model_id: str, max_new_tokens: int) -> MlxDescribeHandle:
    from mlx_vlm import load

    model, processor = load(resolve_model(model_id))
    return MlxDescribeHandle(model, processor, max_new_tokens)
