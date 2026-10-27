import pytest

from docparse.models import Registry, RegistryError
from docparse.models.registry import default_backend, default_specs

KEYS = ["pymupdf", "layout", "ocr", "vl", "embedding", "describe"]


def test_all_components_with_required_fields():
    reg = Registry.load(None)
    assert reg.keys() == KEYS
    for spec in reg.specs():
        assert spec.task and spec.name and spec.device in {"cpu", "gpu", "mlx", "mps"} and spec.vram_mb >= 0


def test_pymupdf_is_cpu_with_zero_vram():
    spec = Registry.load(None).get("pymupdf")
    assert (spec.device, spec.vram_mb) == ("cpu", 0)


def test_unknown_key_lists_valid_keys():
    with pytest.raises(RegistryError, match="valid keys: pymupdf, layout"):
        Registry.load(None).get("nope")


def test_vl_defaults_are_bounded_and_keep_headers():
    params = Registry.load(None).get("vl").params
    assert params["max_new_tokens"] > 0 and params["timeout_s"] > 0
    assert params["markdown_ignore_labels"] == []


def test_override_changes_only_that_model(tmp_path):
    cfg = tmp_path / "models.toml"
    cfg.write_text("[models.vl.params]\ntimeout_s = 30\n")
    reg = Registry.load(cfg)
    assert reg.get("vl").params["timeout_s"] == 30
    assert reg.get("vl").params["max_new_tokens"] == Registry.load(None).get("vl").params["max_new_tokens"]
    assert reg.get("ocr") == Registry.load(None).get("ocr")


def test_unknown_parameter_names_file_and_parameter(tmp_path):
    cfg = tmp_path / "models.toml"
    cfg.write_text("[models.vl.params]\ntimeout = 30\n")
    with pytest.raises(RegistryError, match=r"models\.toml.*'timeout'.*'vl'"):
        Registry.load(cfg)


def test_unknown_model_in_config(tmp_path):
    cfg = tmp_path / "models.toml"
    cfg.write_text("[models.vlm.params]\nx = 1\n")
    with pytest.raises(RegistryError, match="unknown model 'vlm'"):
        Registry.load(cfg)


def test_budget_override(tmp_path):
    cfg = tmp_path / "models.toml"
    cfg.write_text("[budget]\ntotal_mb = 24000\n")
    assert Registry.load(cfg).budget.total_mb == 24000


def test_all_models_together_do_not_fit():
    reg = Registry.load(None)
    fit = reg.fits(reg.keys())
    assert not fit.ok and fit.needed_mb == sum(s.vram_mb for s in reg.specs())
    assert fit.budget_mb == reg.budget.usable_mb
    assert "does not fit" in str(fit)


def test_ocr_and_layout_fit_together():
    assert Registry.load(None).fits(["ocr", "layout"]).ok


def test_repo_models_toml_is_valid():
    assert Registry.load().get("embedding").params["model_id"] == "google/embeddinggemma-2"


def test_describe_is_separate_from_vl_and_has_a_model_id():
    params = Registry.load(None).get("describe").params
    assert params["model_id"] == "Qwen/Qwen2.5-VL-3B-Instruct"
    assert params["max_new_tokens"] > 0
    assert Registry.load(None).get("describe").name != Registry.load(None).get("vl").name


def test_default_backend_follows_platform(monkeypatch):
    monkeypatch.setattr("docparse.models.registry.sys.platform", "darwin")
    assert default_backend() == "mlx"
    for key in ("vl", "embedding", "describe"):
        assert default_specs()[key].params["backend"] == "mlx"
        assert default_specs()[key].device == "mlx"
    monkeypatch.setattr("docparse.models.registry.sys.platform", "linux")
    assert default_backend() == "cuda"
    for key in ("vl", "embedding", "describe"):
        assert default_specs()[key].params["backend"] == "cuda"
        assert default_specs()[key].device == "gpu"


def test_backend_override(tmp_path):
    cfg = tmp_path / "models.toml"
    cfg.write_text("[models.vl.params]\nbackend = \"cuda\"\n")
    reg = Registry.load(cfg)
    assert reg.get("vl").params["backend"] == "cuda"
    assert reg.get("embedding") == Registry.load(None).get("embedding")


def test_device_override(tmp_path):
    cfg = tmp_path / "models.toml"
    cfg.write_text("[models.embedding]\ndevice = \"cpu\"\n")
    assert Registry.load(cfg).get("embedding").device == "cpu"


def test_platform_budget_override_changes_fit(tmp_path):
    cfg = tmp_path / "models.toml"
    cfg.write_text("[budget]\ntotal_mb = 24576\nreserve_mb = 1024\n")
    reg = Registry.load(cfg)
    assert reg.budget.total_mb == 24576
    # the full set does not fit at 8 GB but does at 24 GB unified memory
    assert reg.fits(reg.keys()).ok
