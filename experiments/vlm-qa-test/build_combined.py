"""Join questions.py + raw_<backend>.json + judgments.py into one report-ready file.

Not production code; see experiments/vlm-qa-test/README.md for context. Run whenever a new
backend is added or judgments.py is updated:

    /snap/bin/uv run python experiments/vlm-qa-test/build_combined.py

Writes combined_results.json: one row per question, with the page image path, ground truth,
and every backend's answer + verdict + note + timing/cost side by side. This is the single file
a future visual report (HTML page, notebook, whatever) should read -- it should never need to
re-join raw_*.json and judgments.py itself.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from questions import QUESTIONS  # noqa: E402
from judgments import JUDGMENTS  # noqa: E402

# backend key -> raw_<...>.json filename (not always backend == filename stem, e.g. paddle)
RAW_FILES = {
    "qwen3b": "raw_qwen3b.json",
    "qwen7b": "raw_qwen7b.json",
    "gemma": "raw_gemma.json",
    "paddle_vl": "raw_paddle_vl.json",
    "gemini_argon": "raw_gemini_argon.json",
}


def load_raw(backend: str) -> dict:
    path = HERE / RAW_FILES[backend]
    data = json.loads(path.read_text())
    by_id = {r["id"]: r for r in data["results"]}
    return data, by_id


def main():
    backends = list(RAW_FILES.keys())
    raw = {b: load_raw(b) for b in backends}

    backend_meta = {}
    for b in backends:
        summary, _ = raw[b]
        meta = {
            "model_variant": summary.get("model_variant"),
            "gen_time_mean_s": summary.get("gen_time_mean_s"),
            "gen_time_median_s": summary.get("gen_time_median_s"),
        }
        if "total_cost_usd" in summary:
            meta["total_cost_usd"] = summary["total_cost_usd"]
            meta["mean_cost_usd_per_question"] = summary["mean_cost_usd_per_question"]
            meta["pricing_usd_per_mtok"] = summary["pricing_usd_per_mtok"]
        if "vram_peak_nvidia_smi_mib" in summary:
            meta["vram_peak_nvidia_smi_mib"] = summary["vram_peak_nvidia_smi_mib"]
        backend_meta[b] = meta

    questions_out = []
    tally = {b: {"correct": 0, "partial": 0, "wrong": 0} for b in backends}

    for q in QUESTIONS:
        qid = q["id"]
        entry = {
            "id": qid,
            "doc": q["doc"],
            "page": q["page"],
            "question": q["question"],
            "ground_truth": q["ground_truth"],
            "answers": {},
        }
        for b in backends:
            _, by_id = raw[b]
            r = by_id.get(qid, {})
            j = JUDGMENTS.get(qid, {}).get(b, {})
            verdict = j.get("verdict", "unjudged")
            if verdict in tally[b]:
                tally[b][verdict] += 1
            answer_entry = {
                "answer": r.get("answer"),
                "gen_time_s": r.get("gen_time_s"),
                "verdict": verdict,
                "note": j.get("note"),
            }
            if "cost_usd" in r:
                answer_entry["cost_usd"] = r["cost_usd"]
                answer_entry["input_tokens"] = r.get("input_tokens")
                answer_entry["output_tokens"] = r.get("output_tokens")
            entry["answers"][b] = answer_entry
        questions_out.append(entry)

    out = {
        "backends": backends,
        "backend_meta": backend_meta,
        "tally": tally,
        "questions": questions_out,
    }

    out_path = HERE / "combined_results.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"wrote {out_path}")
    print(f"{len(questions_out)} questions x {len(backends)} backends")
    print(f"{'backend':14} {'correct':8} {'partial':8} {'wrong':8}")
    for b in backends:
        t = tally[b]
        print(f"{b:14} {t['correct']:<8} {t['partial']:<8} {t['wrong']:<8}")


if __name__ == "__main__":
    main()
