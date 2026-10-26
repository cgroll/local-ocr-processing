"""Document-level title+summary from a cloud flagship model (Gemini 4 Argon, via Vertex AI) --
a second, parallel data source next to the local `describe`-model summary (`summary.py`), built
to compare retrieval quality later (`retrieval-eval`, not part of this change). See
`openspec/changes/cloud-document-summary/` for the proposal/design behind this module.

Uses the same Markdown digest text as the local summary (`document-digest`) as input, so both
are directly comparable (design.md decision 2). Does NOT go through `ModelManager`/the model
registry: a Vertex AI call is a cloud API request, not a local, VRAM-budgeted model (design.md
decision 1) -- callers build a client with `build_client()` (or inject a fake for tests) and
pass it in explicitly.

Client/retry/cost-tracking style is carried over from the informal spike
`experiments/vlm-qa-test/run_gemini_vl.py`: `vertexai=True`, `location="global"` (the regional
endpoint 404s for this model despite Google's docs listing it as supported), an explicit HTTP
timeout (the spike hit a 12+ minute hang with the SDK's default of none), up to 3 attempts, and
cost computed from the response's own `usage_metadata` token counts x published list price, not
estimated.
"""
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..parse.format import RESULTS_DIR
from .document import DIGEST_SUBDIR

GCP_PROJECT = "pi-agent-gemini"
GCP_LOCATION = "global"
MODEL_ID = "gemini-4-argon"
# $ per token, published list price as of 2026-10-25 (see run_gemini_vl.py's MODELS["argon"]).
PRICE_IN_PER_MTOK = 2.00
PRICE_OUT_PER_MTOK = 10.00
HTTP_TIMEOUT_MS = 60_000
MAX_ATTEMPTS = 3

PROMPT_TEMPLATE = """--- DOCUMENT CONTENT (automatically extracted: text, table contents, and \
descriptions of figures/charts) ---
{content}
--- END DOCUMENT CONTENT ---

Based only on the document above: write a short title line, then a 3-5 sentence summary \
paragraph of what this document is and what it covers. Do not list keywords. Format exactly as:
TITLE: <title>
SUMMARY: <paragraph>
"""

_TITLE_RE = re.compile(r"TITLE[ \t]*:[ \t]*(.*)", re.IGNORECASE)
_SUMMARY_RE = re.compile(r"SUMMARY\s*:[ \t]*(.*)", re.IGNORECASE | re.DOTALL)


@dataclass
class CloudDocumentSummary:
    doc_id: str
    title: str
    summary: str
    status: str = "ok"  # "ok" | "error"
    model: str = MODEL_ID
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CloudDocumentSummary":
        return cls(**d)


@dataclass
class CloudSummaryCounts:
    done: int = 0  # documents for which a cloud call was actually made this run
    errors: int = 0
    skipped: int = 0  # documents with an existing `ok` result, left untouched
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    messages: list[str] = field(default_factory=list)


def build_client():
    """Real Vertex AI client. Not used in tests -- those inject a fake object exposing the same
    `.models.generate_content(model=..., contents=...)` shape, so no network access or GCP
    credentials are needed to exercise the retry/parsing/storage logic below."""
    from google import genai
    from google.genai import types
    return genai.Client(
        vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION,
        http_options=types.HttpOptions(timeout=HTTP_TIMEOUT_MS),
    )


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * PRICE_IN_PER_MTOK + (output_tokens / 1_000_000) * PRICE_OUT_PER_MTOK


def parse_cloud_title_summary(raw_output: str, fallback_title: str) -> tuple[str, str]:
    """Deliberately standalone, simpler than `summary.py:parse_title_summary` (design.md
    decision 2): a flagship model's realistic failure mode here is an API/network error, not the
    degenerate generation loops / placeholder-tag echoes the local 3B model produces, so this
    only needs to tolerate a missing TITLE:/SUMMARY: label, not tag clutter."""
    text = raw_output.strip()
    summary_match = _SUMMARY_RE.search(text)
    summary = summary_match.group(1).strip() if summary_match else text
    title_match = _TITLE_RE.search(text)
    title_lines = title_match.group(1).splitlines() if title_match else []
    title = title_lines[0].strip() if title_lines else ""
    return (title or fallback_title), summary


def generate_cloud_summary(client, doc_id: str, digest_text: str) -> CloudDocumentSummary:
    """Calls the cloud model with up to MAX_ATTEMPTS retries. A persistent failure, an empty
    response, or a response that parses down to an empty summary is reported as
    `status="error"` for this document -- never raised -- so a batch run over many documents can
    continue past it (see spec `cloud-document-summary`, "Fehler pro Dokument statt Abbruch")."""
    prompt = PROMPT_TEMPLATE.format(content=digest_text)
    resp = None
    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = client.models.generate_content(model=MODEL_ID, contents=[prompt])
            break
        except Exception as e:  # noqa: BLE001 -- includes the SDK's own timeout error
            last_err = e
            print(f"[cloud-summary] {doc_id} attempt {attempt}/{MAX_ATTEMPTS} failed: {e!r}", file=sys.stderr)

    if resp is None:
        return CloudDocumentSummary(
            doc_id, doc_id, "", status="error",
            error=f"{last_err!r} after {MAX_ATTEMPTS} attempts",
        )

    usage = getattr(resp, "usage_metadata", None)
    in_tok = (usage.prompt_token_count or 0) if usage else 0
    out_tok = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0
    cost = compute_cost(in_tok, out_tok)

    raw_text = (resp.text or "").strip()
    if not raw_text:
        return CloudDocumentSummary(
            doc_id, doc_id, "", status="error",
            input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost, error="empty response",
        )

    title, summary = parse_cloud_title_summary(raw_text, fallback_title=doc_id)
    if not summary.strip():
        return CloudDocumentSummary(
            doc_id, doc_id, "", status="error",
            input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost,
            error="empty summary after parsing",
        )
    return CloudDocumentSummary(
        doc_id, title, summary, status="ok",
        input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost,
    )


def cloud_summary_path(doc_id: str, root: Path = RESULTS_DIR) -> Path:
    return root / DIGEST_SUBDIR / f"{doc_id}.cloud_summary.json"


def write_cloud_summary(summary: CloudDocumentSummary, root: Path = RESULTS_DIR) -> Path:
    path = cloud_summary_path(summary.doc_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def read_cloud_summary(path: Path) -> CloudDocumentSummary:
    return CloudDocumentSummary.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def digest_text_path(doc_id: str, root: Path = RESULTS_DIR) -> Path:
    return root / DIGEST_SUBDIR / f"{doc_id}.md"


def run(
    client, doc_ids: list[str], root: Path = RESULTS_DIR, force: bool = False, log=print,
) -> CloudSummaryCounts:
    """Batch run over `doc_ids`: skips documents that already have an `ok` cloud summary unless
    `force` is set (an existing `error` result is retried automatically, no `force` needed -- see
    spec `cloud-document-summary`, "Wiederholbar und fortsetzbar"). A failing document is
    recorded and the run continues with the rest ("Fehler pro Dokument statt Abbruch")."""
    counts = CloudSummaryCounts()
    for doc_id in doc_ids:
        path = cloud_summary_path(doc_id, root)
        if path.exists() and not force:
            existing = read_cloud_summary(path)
            if existing.status == "ok":
                counts.skipped += 1
                continue

        dp = digest_text_path(doc_id, root)
        if not dp.exists():
            counts.errors += 1
            counts.messages.append(f"{doc_id}: missing digest at {dp}")
            continue

        result = generate_cloud_summary(client, doc_id, dp.read_text(encoding="utf-8"))
        write_cloud_summary(result, root)
        counts.done += 1
        counts.total_input_tokens += result.input_tokens
        counts.total_output_tokens += result.output_tokens
        counts.total_cost_usd += result.cost_usd
        if result.status == "error":
            counts.errors += 1
            counts.messages.append(f"{doc_id}: {result.error}")
        log(
            f"cloud-summary {doc_id:<35} -> {result.status:<5} "
            f"${result.cost_usd:.5f} ({result.input_tokens}in/{result.output_tokens}out tok)"
        )
    return counts
