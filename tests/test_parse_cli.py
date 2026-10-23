from docparse.parse.__main__ import main
from docparse.parse.format import Block, PageResult, write_result


def put(root, engine, page, status="ok", seconds=1.0, bbox=(1, 1, 5, 5)):
    blocks = [Block(type="line", label="l", bbox=list(bbox), engine=engine)] if status == "ok" else []
    write_result(PageResult("d", page, 150, 100, 100, engine, status=status, error="x" if status == "error" else None,
                            seconds=seconds, blocks=blocks), root)


def test_summary_and_validate_without_gpu(tmp_path, capsys):
    put(tmp_path, "ocr", 1, seconds=1.0)
    put(tmp_path, "ocr", 2, seconds=3.0)
    put(tmp_path, "ocr", 3, status="error")
    assert main(["--results-dir", str(tmp_path), "summary"]) == 0
    out = capsys.readouterr().out
    assert "ocr" in out and "line 2" in out and "2.0" in out  # median of 1.0 and 3.0
    assert main(["--results-dir", str(tmp_path), "validate"]) == 0
    put(tmp_path, "ocr", 4, bbox=(1, 1, 500, 5))
    assert main(["--results-dir", str(tmp_path), "validate"]) == 1
    assert "0004.json" in capsys.readouterr().out


def test_summary_on_empty_tree(tmp_path, capsys):
    assert main(["--results-dir", str(tmp_path), "summary"]) == 0
    assert "no results" in capsys.readouterr().out


def test_unknown_engine(capsys):
    assert main(["run", "--engines", "nope"]) == 2
