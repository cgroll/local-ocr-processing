"""Task 6.1: orchestrates the pilot -- a handful of questions x both sandbox variants, each as
one `docker run` of the sandbox image, then judged via Gemini (judge.py). Thin glue; the actual
work happens in run_agent.py (inside the container) and analyze_run.py/judge.py (on the host).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "vlm-qa-test"))

from analyze_run import summarize  # noqa: E402
from questions import QUESTIONS  # noqa: E402

IMAGE = "agentic-retrieval-eval-sandbox"
HF_CACHE = Path.home() / ".cache" / "huggingface"
CLAUDE_CONFIG_DIR = Path("/tmp/claude_config_dir")


def run_one(sandbox_dir: Path, question: str, out_path: Path) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "docker", "run", "--rm",
        "--user", "1000:1000",
        "-v", f"{sandbox_dir}:/sandbox:ro",
        "-v", f"{HF_CACHE}:/hf-cache:ro",
        "-v", f"{CLAUDE_CONFIG_DIR}:/claude-config:ro",
        "-v", f"{out_path.parent}:/output",
        "-e", "CLAUDE_CONFIG_DIR=/claude-config",
        "-e", "HOME=/tmp",
        "-e", "SANDBOX_ROOT=/sandbox",
        IMAGE,
        "python", "sandbox_tools/run_agent.py", question, "--out", f"/output/{out_path.name}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        print(proc.stdout[-2000:], file=sys.stderr)
        print(proc.stderr[-2000:], file=sys.stderr)
        raise RuntimeError(f"docker run failed (exit {proc.returncode})")
    return json.loads(out_path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question-ids", nargs="+", required=True)
    parser.add_argument("--sandboxes-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    questions_by_id = {q["id"]: q for q in QUESTIONS}
    rows = []
    for qid in args.question_ids:
        q = questions_by_id[qid]
        for variant in ("local", "cloud"):
            sandbox_dir = args.sandboxes_dir / f"sandbox_{variant}"
            out_path = args.out_dir / f"{qid}_{variant}.json"
            print(f"=== {qid} [{variant}] ===", file=sys.stderr)
            result = run_one(sandbox_dir, q["question"], out_path)
            summary = summarize(result, variant, qid)
            summary["ground_truth"] = q["ground_truth"]
            rows.append(summary)
            print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)

    (args.out_dir / "pilot_summary.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print(f"wrote {args.out_dir / 'pilot_summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
