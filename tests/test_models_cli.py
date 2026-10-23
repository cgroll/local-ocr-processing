from docparse.models.__main__ import main


def test_list_runs_without_gpu(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    for key in ("pymupdf", "layout", "ocr", "vl", "embedding"):
        assert key in out


def test_check_exit_codes(capsys):
    assert main(["check", "ocr", "layout"]) == 0
    assert main(["check", "vl", "ocr", "layout", "embedding"]) == 1
    assert "does not fit" in capsys.readouterr().out


def test_unknown_key_is_an_error(capsys):
    assert main(["check", "nope"]) == 2
    assert "valid keys" in capsys.readouterr().err
