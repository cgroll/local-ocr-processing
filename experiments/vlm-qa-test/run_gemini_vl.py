"""Informal VLM QA test - Google flagship models via Vertex AI (Gemini 4 Argon / Gemini 3.1 Pro).

Not production code; see experiments/vlm-qa-test/README for context. Auth is via Application
Default Credentials under GCP project "pi-agent-gemini" (same project/account speech-to-speech's
config.py already documents -- org policy blocks plain Gemini-Developer-API keys, so this must
go through Vertex AI). location="global" -- "us-central1" 404s for these two models even though
Google's docs list it as supported; global works for both.

Run with the ephemeral --with deps so no project venv is touched:

    /snap/bin/uv run --with google-genai --with pillow \
        python experiments/vlm-qa-test/run_gemini_vl.py --model argon [--smoke]
    /snap/bin/uv run --with google-genai --with pillow \
        python experiments/vlm-qa-test/run_gemini_vl.py --model pro31 [--smoke]

Tracks real cost per question from the API's own usage_metadata (prompt/candidates/thoughts
token counts) x published per-token pricing, not an estimate -- this is the whole point of this
run (see conversation: "tracke die Kosten, damit ich verstehe wieviel sowas kostet").
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from questions import QUESTIONS  # noqa: E402

GCP_PROJECT = "pi-agent-gemini"
GCP_LOCATION = "global"

# $ per token (published list price, 2026-10-25, prompts <=200K tokens -- true for every
# question here, pages are single images). "output" price applies to candidates tokens AND
# thinking tokens (3.1 Pro bills reasoning tokens as output).
MODELS = {
    "argon": {
        "model_id": "gemini-4-argon",
        "price_in_per_mtok": 2.00,
        "price_out_per_mtok": 10.00,
    },
    "pro31": {
        "model_id": "gemini-3.1-pro-preview",
        "price_in_per_mtok": 2.00,
        "price_out_per_mtok": 12.00,
    },
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=list(MODELS.keys()))
    parser.add_argument("--smoke", action="store_true", help="run only the first question")
    args = parser.parse_args()

    spec = MODELS[args.model]
    model_id = spec["model_id"]
    questions = QUESTIONS[:1] if args.smoke else QUESTIONS

    from google import genai
    from google.genai import types

    # Default client has no request timeout -- a single stalled/dropped connection can then
    # block forever with zero CPU activity and zero log output (confirmed via a 12+ minute
    # hang on 2026-10-25: TCP connection stayed ESTABLISHED to a Google IP the whole time,
    # process just sitting in wait_woken). 60s is generous given normal calls take 3-10s.
    client = genai.Client(
        vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION,
        http_options=types.HttpOptions(timeout=60_000),
    )

    results = []
    gen_times = []
    total_cost_usd = 0.0
    total_in_tok = 0
    total_out_tok = 0

    for q in questions:
        img_path = REPO_ROOT / q["page"]
        img_bytes = img_path.read_bytes()

        t0 = time.monotonic()
        resp = None
        last_err = None
        for attempt in range(1, 4):
            try:
                resp = client.models.generate_content(
                    model=model_id,
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                        q["question"],
                    ],
                )
                break
            except Exception as e:  # noqa: BLE001 -- includes the SDK's timeout error
                last_err = e
                print(f"[{args.model}] {q['id']} attempt {attempt} failed after "
                      f"{time.monotonic() - t0:.1f}s: {e!r}", file=sys.stderr)
        gen_time = time.monotonic() - t0
        gen_times.append(gen_time)

        if resp is None:
            print(f"[{args.model}] {q['id']}: giving up after 3 attempts", file=sys.stderr)
            results.append({
                "id": q["id"], "question": q["question"],
                "answer": f"[ERROR after 3 attempts: {last_err!r}]",
                "gen_time_s": gen_time, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
            })
            continue

        usage = resp.usage_metadata
        in_tok = usage.prompt_token_count or 0
        out_tok = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        cost = (in_tok / 1_000_000) * spec["price_in_per_mtok"] + \
               (out_tok / 1_000_000) * spec["price_out_per_mtok"]
        total_cost_usd += cost
        total_in_tok += in_tok
        total_out_tok += out_tok

        answer = (resp.text or "").strip()
        print(f"[{args.model}] {q['id']}: {gen_time:.1f}s, {in_tok}in/{out_tok}out tok, "
              f"${cost:.5f} -> {answer!r}", file=sys.stderr)
        results.append({
            "id": q["id"],
            "question": q["question"],
            "answer": answer,
            "gen_time_s": gen_time,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": cost,
        })

    summary = {
        "backend": args.model,
        "model_variant": model_id,
        "gcp_project": GCP_PROJECT,
        "gcp_location": GCP_LOCATION,
        "pricing_usd_per_mtok": {
            "input": spec["price_in_per_mtok"],
            "output": spec["price_out_per_mtok"],
        },
        "gen_times_s": gen_times,
        "gen_time_mean_s": statistics.mean(gen_times) if gen_times else None,
        "gen_time_median_s": statistics.median(gen_times) if gen_times else None,
        "total_input_tokens": total_in_tok,
        "total_output_tokens": total_out_tok,
        "total_cost_usd": total_cost_usd,
        "mean_cost_usd_per_question": total_cost_usd / len(questions) if questions else None,
        "results": results,
    }

    out_name = f"raw_gemini_{args.model}.smoke.json" if args.smoke else f"raw_gemini_{args.model}.json"
    out_path = Path(__file__).resolve().parent / out_name
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"[{args.model}] wrote {out_path}", file=sys.stderr)
    print(f"[{args.model}] mean_gen={summary['gen_time_mean_s']:.1f}s "
          f"total_tokens={total_in_tok}in/{total_out_tok}out "
          f"total_cost=${total_cost_usd:.4f} "
          f"(~${summary['mean_cost_usd_per_question']*1000:.2f} per 1000 questions)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
