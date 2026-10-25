"""Answer a single question with PaddleOCR-VL-1.6, writing the result to --out as JSON.

Internal helper for run_paddle_vl.py. Loads the model fresh per invocation. This is a
deliberate deviation from the "load once, loop over questions" pattern used by the other
backends: in testing, PaddleOCR-VL's DocVLM.predict() bypass path showed reproducible but
non-deterministic catastrophic slowdowns (100% CPU, 0% GPU util -- a Python-level hang, not
a GPU/precision issue) that an in-process SIGALRM watchdog could not reliably interrupt
(likely blocked in a GIL-held C/C++ call). Running one question per OS process lets the
orchestrator (run_paddle_vl.py) apply a hard `timeout` kill that always works. Model load is
cheap here (~1-2s), so the overhead is acceptable for 20 one-shot calls.
"""
import argparse
import json
import os
import sys
import time

# Fixes a real hang (not the generate()-loop slowdown described in run_paddle_vl.py's
# docstring): PaddlePaddle's default "auto_growth" GPU allocator can get stuck in an
# infinite ioctl retry loop against the NVIDIA kernel module -- 0% GPU util, one CPU core
# pegged, no error, no timeout, forever. Confirmed root cause and fix via
# https://github.com/PaddlePaddle/PaddleOCR/issues/17693. Must be set before paddle is
# imported (including transitively via paddlex/paddleocr below).
os.environ.setdefault("FLAGS_allocator_strategy", "naive_best_fit")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=100)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    from paddlex.inference.models.doc_vlm.modeling.paddleocr_vl._paddleocr_vl import (
        PaddleOCRVLForConditionalGeneration,
    )
    PaddleOCRVLForConditionalGeneration._keep_in_fp32_modules = None
    from paddleocr import DocVLM

    t0 = time.monotonic()
    model = DocVLM(model_name="PaddleOCR-VL-1.6-0.9B")
    load_time = time.monotonic() - t0
    print(f"[paddle-one] loaded in {load_time:.1f}s", file=sys.stderr)

    t0 = time.monotonic()
    out = model.predict(
        {"image": args.image, "query": args.question},
        max_new_tokens=args.max_new_tokens, use_cache=True,
    )
    gen_time = time.monotonic() - t0

    item = out[0] if isinstance(out, (list, tuple)) else out
    answer = None
    for key in ("result", "res", "text", "content"):
        try:
            if hasattr(item, "__getitem__"):
                answer = item[key]
                break
        except Exception:
            pass
    if answer is None:
        answer = getattr(item, "result", None)
    if answer is None:
        try:
            answer = dict(item)
        except Exception:
            answer = repr(item)

    with open(args.out, "w") as f:
        json.dump({
            "answer": answer if isinstance(answer, str) else str(answer),
            "load_time_s": load_time,
            "gen_time_s": gen_time,
        }, f)
    print(f"[paddle-one] done in {gen_time:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
