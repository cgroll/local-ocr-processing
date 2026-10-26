from pathlib import Path

import pytest

from docparse.digest.cloud_summary import (
    CloudDocumentSummary,
    cloud_summary_path,
    compute_cost,
    digest_text_path,
    generate_cloud_summary,
    parse_cloud_title_summary,
    read_cloud_summary,
    run,
    write_cloud_summary,
)


class FakeModels:
    """Stands in for `client.models` -- `generate_cloud_summary` only ever calls
    `client.models.generate_content(model=..., contents=...)`."""

    def __init__(self, responses):
        # Each entry is either a FakeResponse or an Exception instance/class to raise.
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, model, contents):
        self.calls.append((model, contents))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


class FakeUsage:
    def __init__(self, prompt_token_count=10, candidates_token_count=20, thoughts_token_count=0):
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count
        self.thoughts_token_count = thoughts_token_count


class FakeResponse:
    def __init__(self, text, usage=None):
        self.text = text
        self.usage_metadata = usage if usage is not None else FakeUsage()


# --- parse_cloud_title_summary -------------------------------------------------

def test_parses_exact_format():
    title, summary = parse_cloud_title_summary("TITLE: LM317\nSUMMARY: An adjustable regulator.", "fallback")
    assert title == "LM317" and summary == "An adjustable regulator."


def test_missing_title_falls_back_to_doc_id():
    title, summary = parse_cloud_title_summary("SUMMARY: Just a summary.", "ds-lm317")
    assert title == "ds-lm317" and summary == "Just a summary."


def test_no_labels_uses_whole_output_as_summary():
    title, summary = parse_cloud_title_summary("Plain prose, no labels.", "ds-x")
    assert title == "ds-x" and summary == "Plain prose, no labels."


# --- compute_cost ---------------------------------------------------------------

def test_compute_cost_uses_published_price_per_mtok():
    # 1,000,000 in-tokens at $2.00/Mtok + 500,000 out-tokens at $10.00/Mtok = $2.00 + $5.00
    assert compute_cost(1_000_000, 500_000) == pytest.approx(7.00)


def test_compute_cost_zero_tokens_is_zero():
    assert compute_cost(0, 0) == 0.0


# --- generate_cloud_summary: success, retry, exhaustion, empty responses -------

def test_successful_call_returns_ok_with_cost_and_tokens():
    client = FakeClient([FakeResponse("TITLE: X\nSUMMARY: Y.", FakeUsage(100, 50, 0))])
    result = generate_cloud_summary(client, "doc-1", "digest text")
    assert result == CloudDocumentSummary(
        "doc-1", "X", "Y.", status="ok", input_tokens=100, output_tokens=50,
        cost_usd=compute_cost(100, 50),
    )
    assert client.models.calls[0][0] == "gemini-4-argon"
    assert "digest text" in client.models.calls[0][1][0]


def test_retries_then_succeeds():
    client = FakeClient([RuntimeError("boom"), RuntimeError("boom again"), FakeResponse("TITLE: X\nSUMMARY: Y.")])
    result = generate_cloud_summary(client, "doc-1", "digest text")
    assert result.status == "ok"
    assert len(client.models.calls) == 3


def test_exhausted_retries_marks_error_without_raising():
    client = FakeClient([RuntimeError("a"), RuntimeError("b"), RuntimeError("c")])
    result = generate_cloud_summary(client, "doc-1", "digest text")
    assert result.status == "error"
    assert result.title == "doc-1" and result.summary == ""
    assert "after 3 attempts" in result.error
    assert len(client.models.calls) == 3


def test_empty_response_text_is_an_error():
    client = FakeClient([FakeResponse("   ")])
    result = generate_cloud_summary(client, "doc-1", "digest text")
    assert result.status == "error" and result.error == "empty response"
    # tokens/cost from the (otherwise wasted) call are still recorded
    assert result.input_tokens == 10


def test_summary_that_parses_to_empty_is_an_error():
    client = FakeClient([FakeResponse("TITLE: X\nSUMMARY:")])
    result = generate_cloud_summary(client, "doc-1", "digest text")
    assert result.status == "error" and result.error == "empty summary after parsing"


def test_content_before_instruction_like_the_local_prompt():
    client = FakeClient([FakeResponse("TITLE: X\nSUMMARY: Y.")])
    generate_cloud_summary(client, "doc-1", "THE DOCUMENT BODY")
    prompt = client.models.calls[0][1][0]
    assert prompt.index("THE DOCUMENT BODY") < prompt.index("write a short title line")


# --- read/write round trip -------------------------------------------------------

def test_cloud_summary_round_trip(tmp_path):
    summary = CloudDocumentSummary(
        "doc-1", "Title", "Summary text", status="ok", input_tokens=5, output_tokens=7, cost_usd=0.0001,
    )
    path = write_cloud_summary(summary, tmp_path)
    assert read_cloud_summary(path) == summary


def test_cloud_summary_path_is_separate_from_local_summary_path(tmp_path):
    path = cloud_summary_path("doc-1", tmp_path)
    assert path.name == "doc-1.cloud_summary.json"
    assert not path.name.endswith(".summary.json")


# --- run: resumable batch over several documents ---------------------------------

def _write_digest(root: Path, doc_id: str, text: str = "digest content") -> None:
    path = digest_text_path(doc_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_run_processes_every_document_with_a_digest(tmp_path):
    _write_digest(tmp_path, "doc-1")
    _write_digest(tmp_path, "doc-2")
    client = FakeClient([FakeResponse("TITLE: A\nSUMMARY: B."), FakeResponse("TITLE: C\nSUMMARY: D.")])
    counts = run(client, ["doc-1", "doc-2"], tmp_path, log=lambda *a: None)
    assert counts.done == 2 and counts.errors == 0 and counts.skipped == 0
    assert read_cloud_summary(cloud_summary_path("doc-1", tmp_path)).title == "A"
    assert read_cloud_summary(cloud_summary_path("doc-2", tmp_path)).title == "C"


def test_second_run_without_changes_skips_everything(tmp_path):
    _write_digest(tmp_path, "doc-1")
    client = FakeClient([FakeResponse("TITLE: A\nSUMMARY: B.")])
    run(client, ["doc-1"], tmp_path, log=lambda *a: None)

    client2 = FakeClient([])  # no response queued -- a second call would raise IndexError
    counts = run(client2, ["doc-1"], tmp_path, log=lambda *a: None)
    assert counts.done == 0 and counts.skipped == 1
    assert client2.models.calls == []


def test_force_recomputes_an_existing_ok_result(tmp_path):
    _write_digest(tmp_path, "doc-1")
    client = FakeClient([FakeResponse("TITLE: A\nSUMMARY: B.")])
    run(client, ["doc-1"], tmp_path, log=lambda *a: None)

    client2 = FakeClient([FakeResponse("TITLE: NEW\nSUMMARY: Replaced.")])
    counts = run(client2, ["doc-1"], tmp_path, force=True, log=lambda *a: None)
    assert counts.done == 1
    assert read_cloud_summary(cloud_summary_path("doc-1", tmp_path)).title == "NEW"


def test_a_failing_document_does_not_stop_the_rest_of_the_run(tmp_path):
    _write_digest(tmp_path, "doc-1")
    _write_digest(tmp_path, "doc-2")
    client = FakeClient([
        RuntimeError("x"), RuntimeError("y"), RuntimeError("z"),  # doc-1 exhausts retries
        FakeResponse("TITLE: OK\nSUMMARY: Fine."),  # doc-2 succeeds
    ])
    counts = run(client, ["doc-1", "doc-2"], tmp_path, log=lambda *a: None)
    assert counts.done == 2 and counts.errors == 1
    assert read_cloud_summary(cloud_summary_path("doc-1", tmp_path)).status == "error"
    assert read_cloud_summary(cloud_summary_path("doc-2", tmp_path)).status == "ok"


def test_a_previously_errored_document_is_retried_without_force(tmp_path):
    _write_digest(tmp_path, "doc-1")
    client = FakeClient([RuntimeError("x"), RuntimeError("y"), RuntimeError("z")])
    run(client, ["doc-1"], tmp_path, log=lambda *a: None)
    assert read_cloud_summary(cloud_summary_path("doc-1", tmp_path)).status == "error"

    client2 = FakeClient([FakeResponse("TITLE: Fixed\nSUMMARY: Now it works.")])
    counts = run(client2, ["doc-1"], tmp_path, log=lambda *a: None)  # no --force
    assert counts.done == 1 and counts.skipped == 0
    assert read_cloud_summary(cloud_summary_path("doc-1", tmp_path)).status == "ok"


def test_missing_digest_is_recorded_as_an_error_without_crashing(tmp_path):
    counts = run(FakeClient([]), ["ghost-doc"], tmp_path, log=lambda *a: None)
    assert counts.errors == 1 and counts.done == 0
    assert "missing digest" in counts.messages[0]


def test_cost_and_token_aggregation_sums_only_calls_actually_made(tmp_path):
    _write_digest(tmp_path, "doc-1")
    _write_digest(tmp_path, "doc-2")
    client = FakeClient([
        FakeResponse("TITLE: A\nSUMMARY: B.", FakeUsage(100, 50, 0)),
        FakeResponse("TITLE: C\nSUMMARY: D.", FakeUsage(200, 80, 0)),
    ])
    counts = run(client, ["doc-1", "doc-2"], tmp_path, log=lambda *a: None)
    assert counts.total_input_tokens == 300 and counts.total_output_tokens == 130
    assert counts.total_cost_usd == pytest.approx(compute_cost(100, 50) + compute_cost(200, 80))

    # a second run with everything already ok must not add to a fresh aggregation
    client2 = FakeClient([])
    counts2 = run(client2, ["doc-1", "doc-2"], tmp_path, log=lambda *a: None)
    assert counts2.total_input_tokens == 0 and counts2.total_cost_usd == 0.0
