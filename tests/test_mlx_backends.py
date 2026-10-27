"""Unit tests for the MLX backend handles. These do NOT load real models -- they inject fakes to
check each handle mirrors the call surface the rest of the pipeline relies on (encode/recognise/
describe/generate_text) and returns the expected shapes/types. The real-model smoke runs are
`uv run python -m docparse.models smoke <key>` on Apple Silicon (see tasks 4.2/5.2/6.1)."""
import numpy as np
import pytest

from docparse.models.mlx_backends import (
    MlxDescribeHandle,
    MlxEmbeddingHandle,
    MlxVlHandle,
    vl_prompt_for_label,
)


def test_vl_prompt_mapping():
    assert vl_prompt_for_label("table") == "Table Recognition:"
    assert vl_prompt_for_label("chart") == "Chart Recognition:"
    assert vl_prompt_for_label("formula") == "Formula Recognition:"
    assert vl_prompt_for_label("text") == "OCR:"
    assert vl_prompt_for_label("anything-unmapped") == "OCR:"


class _FakeEmbeds:
    def __init__(self, arr):
        self.text_embeds = arr


class _FakeTokenizer:
    def __call__(self, texts, padding=True, return_tensors="np"):
        self.seen = texts
        return {"input_ids": np.zeros((1, 4), dtype=np.int64)}


class _FakeEmbedModel:
    def __init__(self, dim=768):
        self.dim = dim

    def __call__(self, **kwargs):
        import mlx.core as mx

        # a non-normalised vector so we can verify the handle L2-normalises it
        return _FakeEmbeds(mx.array([[float(i + 1) for i in range(self.dim)]]))


class _FakeEmbedProcessor:
    def __init__(self):
        self.tokenizer = _FakeTokenizer()


mlx = pytest.importorskip("mlx.core")


def test_embedding_handle_text_returns_normalised_768():
    h = MlxEmbeddingHandle(_FakeEmbedModel(), _FakeEmbedProcessor(), dim=768)
    vec = h.encode("hallo welt", prompt_name="Document")
    assert isinstance(vec, np.ndarray) and vec.dtype == np.float32
    assert vec.shape == (768,)
    assert np.isclose(np.linalg.norm(vec), 1.0, atol=1e-5)


def test_embedding_handle_applies_prompt_prefix():
    model = _FakeEmbedModel()
    proc = _FakeEmbedProcessor()
    h = MlxEmbeddingHandle(model, proc, dim=768)
    h.encode("query text", prompt_name="SearchQuery")
    assert proc.tokenizer.seen[0].startswith("task: search result | query: ")


def test_embedding_handle_truncates_to_dim():
    h = MlxEmbeddingHandle(_FakeEmbedModel(dim=768), _FakeEmbedProcessor(), dim=256)
    vec = h.encode("x", prompt_name="Document")
    assert vec.shape == (256,)
    assert np.isclose(np.linalg.norm(vec), 1.0, atol=1e-5)


class _FakeGenResult:
    def __init__(self, text):
        self.text = text


def test_vl_handle_recognise(monkeypatch):
    h = MlxVlHandle(model=type("M", (), {"config": {}})(), processor=object(), layout_detector=None, max_new_tokens=100)
    monkeypatch.setattr("mlx_vlm.prompt_utils.apply_chat_template", lambda *a, **k: "PROMPT")
    monkeypatch.setattr("mlx_vlm.generate", lambda **k: _FakeGenResult("  recognised  "))
    assert h.recognise("/tmp/x.png", "OCR:") == "recognised"


def test_describe_handle_methods(monkeypatch):
    h = MlxDescribeHandle(model=type("M", (), {"config": {}})(), processor=object(), max_new_tokens=50)
    monkeypatch.setattr("mlx_vlm.prompt_utils.apply_chat_template", lambda *a, **k: "PROMPT")
    monkeypatch.setattr("mlx_vlm.generate", lambda **k: _FakeGenResult("a description"))
    assert h.generate_text("summarise this") == "a description"


class _FakeLayoutDetector:
    """Returns two regions: a text block and a table block, in the paddleocr box format."""

    def predict(self, image_bgr):
        return [{"boxes": [
            {"label": "text", "coordinate": [0, 0, 50, 20], "polygon_points": None},
            {"label": "table", "coordinate": [0, 30, 50, 60], "polygon_points": None},
        ]}]


def test_vl_parse_page_composes_blocks(monkeypatch):
    """The MLX VL handle detects regions, recognises each with a task-specific prompt, converts OTSL
    tables to HTML, and returns the raw dicts parse/adapters/vl.py consumes -- in reading order."""
    np_img = np.zeros((80, 60, 3), dtype=np.uint8)

    seen_prompts = []

    def fake_recognise(self, image_path, prompt, *, max_tokens=None):
        seen_prompts.append(prompt)
        # text region -> plain text; table region -> an OTSL token stream
        return "some text" if prompt == "OCR:" else "<fcel>A<fcel>B<nl>"

    monkeypatch.setattr(MlxVlHandle, "recognise", fake_recognise)
    h = MlxVlHandle(model=object(), processor=object(), layout_detector=_FakeLayoutDetector(), max_new_tokens=100)
    raw = h.parse_page(np_img)

    assert [b["label"] for b in raw] == ["text", "table"]  # reading order: top region first
    assert seen_prompts == ["OCR:", "Table Recognition:"]
    assert raw[0]["content"] == "some text"
    assert "<table" in raw[1]["content"].lower()  # OTSL converted to HTML


def test_vl_parse_page_output_feeds_adapter(monkeypatch):
    """End-to-end on the format boundary: parse_page output -> vl.to_blocks yields valid Blocks with
    the same required fields the CUDA path produces (engine 'vl', table block carries html)."""
    from docparse.parse.adapters import vl as vl_adapter

    np_img = np.zeros((80, 60, 3), dtype=np.uint8)
    monkeypatch.setattr(
        MlxVlHandle, "recognise",
        lambda self, p, prompt, max_tokens=None: "para text" if prompt == "OCR:" else "<fcel>A<fcel>B<nl>",
    )
    h = MlxVlHandle(model=object(), processor=object(), layout_detector=_FakeLayoutDetector(), max_new_tokens=100)
    blocks = vl_adapter.to_blocks(h.parse_page(np_img))

    assert all(b.engine == "vl" for b in blocks)
    table = next(b for b in blocks if b.type == "table")
    assert table.html and "<table" in table.html.lower()
    text = next(b for b in blocks if b.type == "text")
    assert text.text == "para text"
