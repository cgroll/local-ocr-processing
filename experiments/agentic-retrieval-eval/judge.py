"""Task 5.1: LLM-as-judge for the agent's answers, using Gemini 4 Argon (Vertex AI) -- bewusst
NICHT Claude, damit nicht dieselbe Modellfamilie ihre eigene Antwort bewertet (proposal.md).

Client/retry/cost pattern copied from `src/docparse/digest/cloud_summary.py` (same GCP
project/location, same `usage_metadata`-based cost accounting), but a standalone script under
`experiments/` with its own prompt/parser -- this is not part of the production pipeline and
does not touch `cloud_summary.py`.

Usage:
    uv run --with google-genai python experiments/agentic-retrieval-eval/judge.py \\
        --question "..." --ground-truth "..." --answer "..."
"""
import argparse
import re
import sys
from dataclasses import asdict, dataclass

GCP_PROJECT = "pi-agent-gemini"
GCP_LOCATION = "global"
MODEL_ID = "gemini-4-argon"
PRICE_IN_PER_MTOK = 2.00
PRICE_OUT_PER_MTOK = 10.00
HTTP_TIMEOUT_MS = 60_000
MAX_ATTEMPTS = 3

PROMPT_TEMPLATE = """\
You are grading one answer from an automated retrieval agent against a known-correct reference
answer. Be strict about factual correctness, but ignore phrasing/formatting differences.

Question: {question}
Reference (ground truth) answer: {ground_truth}
Agent's answer: {agent_answer}

Respond in exactly this format:
VERDICT: <correct|partial|wrong>
REASON: <one short sentence>
"""

_VERDICT_RE = re.compile(r"VERDICT:\s*(correct|partial|wrong)", re.IGNORECASE)
_REASON_RE = re.compile(r"REASON:\s*(.+)", re.IGNORECASE | re.DOTALL)


@dataclass
class JudgeVerdict:
    verdict: str  # "correct" | "partial" | "wrong" | "error"
    reason: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def build_client():
    from google import genai
    from google.genai import types
    return genai.Client(
        vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION,
        http_options=types.HttpOptions(timeout=HTTP_TIMEOUT_MS),
    )


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * PRICE_IN_PER_MTOK + (output_tokens / 1_000_000) * PRICE_OUT_PER_MTOK


def judge_answer(client, question: str, ground_truth: str, agent_answer: str) -> JudgeVerdict:
    prompt = PROMPT_TEMPLATE.format(question=question, ground_truth=ground_truth, agent_answer=agent_answer)
    resp = None
    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = client.models.generate_content(model=MODEL_ID, contents=[prompt])
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[judge] attempt {attempt}/{MAX_ATTEMPTS} failed: {e!r}", file=sys.stderr)

    if resp is None:
        return JudgeVerdict("error", f"{last_err!r} after {MAX_ATTEMPTS} attempts")

    usage = getattr(resp, "usage_metadata", None)
    in_tok = (usage.prompt_token_count or 0) if usage else 0
    out_tok = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0
    cost = compute_cost(in_tok, out_tok)

    raw_text = (resp.text or "").strip()
    verdict_match = _VERDICT_RE.search(raw_text)
    reason_match = _REASON_RE.search(raw_text)
    if not verdict_match:
        return JudgeVerdict("error", f"unparseable judge output: {raw_text[:200]!r}", in_tok, out_tok, cost)
    return JudgeVerdict(
        verdict_match.group(1).lower(),
        reason_match.group(1).strip() if reason_match else "",
        in_tok, out_tok, cost,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--answer", required=True)
    args = parser.parse_args(argv)

    client = build_client()
    result = judge_answer(client, args.question, args.ground_truth, args.answer)
    import json
    print(json.dumps(result.to_dict(), indent=1, ensure_ascii=False))
    return 0 if result.verdict != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
