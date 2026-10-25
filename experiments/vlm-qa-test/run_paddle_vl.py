"""Informal VLM QA test - PaddleOCR-VL-1.6 backend.

Not production code (see experiments/vlm-qa-test/README for context). Run from repo root with:
    /snap/bin/uv run python experiments/vlm-qa-test/run_paddle_vl.py [--smoke]

--smoke runs only the first question to fail fast before burning time on the full 20.

Diagnosed slowdown (2026-10-25): model.predict(..., max_new_tokens=512) could hang for 10+
minutes on some pages even though the very first-ever invocation in this session finished in
9.1s. Live nvidia-smi monitoring during a hung call showed 0% GPU utilization and idle-level
power draw (~35W) while the Python process sat at 100% CPU -- i.e. not a GPU/precision/cache
issue (bf16 weights on GPU confirmed, use_cache=True already paddlex's internal default, no
leftover IPC/shared-memory state from earlier crashes). Binary search via paddlex's lower-level
pred.predict() showed generation is reliably fast through ~100 tokens (2.12s) but blows up
catastrophically somewhere between 100-150 tokens -- consistent with a Python-level (non-GPU)
bottleneck in paddlex's custom generate()/stopping-criteria loop for this bypass (DocVLM) path,
not the normal PaddleOCRVL pipeline this project actually ships. Mitigation: cap max_new_tokens
at 100 (short answers only, no full markdown dumps). An in-process SIGALRM watchdog was tried
first but could NOT reliably interrupt the hang (it's blocked in a GIL-held C/C++ call, so the
signal handler never runs). Fix: run each question in its own OS subprocess
(_paddle_one_question.py) under a hard `timeout` command, which kills at the OS level and always
works regardless of what the child is stuck in. Model load is cheap (~1-2s), so reloading it
once per question is acceptable for 20 one-shot calls.
"""
import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from questions import QUESTIONS  # noqa: E402

OUT_PATH = SCRIPT_DIR / "raw_paddle_vl.json"
ONE_QUESTION_SCRIPT = SCRIPT_DIR / "_paddle_one_question.py"


def nvidia_smi_used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(out.splitlines()[0])


PER_QUESTION_TIMEOUT_S = 90


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="run only the first question")
    args = parser.parse_args()

    questions = QUESTIONS[:1] if args.smoke else QUESTIONS

    vram_before = nvidia_smi_used_mib()
    vram_peak_smi = vram_before

    results = []
    gen_times = []
    load_times = []
    for q in questions:
        img_path = str(REPO_ROOT / q["page"])
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        wall_t0 = time.monotonic()
        proc = subprocess.run(
            [
                "timeout", str(PER_QUESTION_TIMEOUT_S),
                sys.executable, str(ONE_QUESTION_SCRIPT),
                "--image", img_path,
                "--question", q["question"],
                "--max-new-tokens", "100",
                "--out", str(tmp_path),
            ],
            capture_output=True, text=True,
        )
        wall_time = time.monotonic() - wall_t0
        timed_out = proc.returncode == 124

        if timed_out:
            answer = f"[TIMEOUT after {PER_QUESTION_TIMEOUT_S}s, no answer]"
            gen_time = wall_time
            print(f"[paddle-vl] {q['id']} TIMEOUT, child stderr tail:\n"
                  f"{proc.stderr[-1500:]}", file=sys.stderr)
        elif proc.returncode != 0:
            answer = f"[subprocess error, returncode={proc.returncode}: {proc.stderr[-500:]!r}]"
            gen_time = wall_time
        else:
            payload = json.loads(tmp_path.read_text())
            answer = payload["answer"]
            gen_time = payload["gen_time_s"]
            load_times.append(payload["load_time_s"])

        tmp_path.unlink(missing_ok=True)
        gen_times.append(gen_time)
        vram_peak_smi = max(vram_peak_smi, nvidia_smi_used_mib())

        print(f"[paddle-vl] {q['id']}: {gen_time:.1f}s -> {answer!r}", file=sys.stderr)
        results.append({
            "id": q["id"],
            "question": q["question"],
            "answer": answer if isinstance(answer, str) else str(answer),
            "gen_time_s": gen_time,
            "timed_out": timed_out,
        })

    summary = {
        "backend": "paddleocr-vl-1.6-0.9b",
        "model_variant": "PaddleOCR-VL-1.6-0.9B",
        "load_time_mean_s": statistics.mean(load_times) if load_times else None,
        "gen_times_s": gen_times,
        "gen_time_mean_s": statistics.mean(gen_times) if gen_times else None,
        "gen_time_median_s": statistics.median(gen_times) if gen_times else None,
        "vram_peak_nvidia_smi_mib": vram_peak_smi,
        "vram_before_mib": vram_before,
        "results": results,
    }

    out_path = OUT_PATH if not args.smoke else OUT_PATH.with_suffix(".smoke.json")
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"[paddle-vl] wrote {out_path}", file=sys.stderr)
    load_mean = summary["load_time_mean_s"]
    load_str = f"{load_mean:.1f}s" if load_mean is not None else "n/a"
    gen_mean = summary["gen_time_mean_s"]
    gen_str = f"{gen_mean:.1f}s" if gen_mean is not None else "n/a"
    print(f"[paddle-vl] load_mean={load_str} mean_gen={gen_str} "
          f"vram_peak_smi={vram_peak_smi}MiB", file=sys.stderr)


if __name__ == "__main__":
    main()
