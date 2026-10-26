"""Follow-up to the informal VLM QA test: does giving a *text* LLM the already-extracted
structured content (markdown/HTML from `docparse.parse`) instead of the raw page image fix the
"trap" questions where every local VLM misread a dense table or a graph?

Not production code; see experiments/vlm-qa-test/README.md for context on why these five
questions (1b, 3a, 3b, 5a, 8a) were picked -- they're the ones where multiple/all local VLMs
failed together on column/row mix-ups or curve-to-legend matching.

This reuses the same model (Qwen2.5-VL-7B-Instruct) as the `qwen7b` backend in the original test,
but feeds it extracted blocks as plain text (no image) -- isolating "can the model read the fact
if it doesn't have to visually parse the table/graph itself" from "can the model visually parse
a dense table/graph".

**Not all 5 trap questions have a usable structured source**, which is itself a finding:
- 1b (ds-lm317 table): VL ran fine for this doc, gives a clean HTML table.
- 8a (gd1-001147 table): VL was not run for this doc; pymupdf gives a clean HTML table (it's a
  native PDF) -- works just as well here.
- 3a (ds-tps62130 schematic): VL timed out (180s, see README "Bugs found" / the Oct-2026 vl rerun
  log) on all 6 pages of this doc. Falls back to pymupdf's raw positioned text blocks (bbox +
  text, no table structure -- a schematic isn't a table) to test whether bbox proximity alone
  lets the model infer which capacitor sits at the VOS/output net.
- 3b (efficiency-vs-current graph) and 5a (handwritten-style dimension on a scanned drawing) are
  SKIPPED: no text extraction captures what's needed (3b needs curve-color-to-legend matching,
  which is pixel-only information with no text proxy; 5a's VL run timed out and PP-OCRv6's line
  OCR on that page is too garbled to contain the right fraction at all -- see SKIP_REASONS).
  Feeding the model garbage text would not be a fair test of the hypothesis.

Run with the ephemeral --with deps so the project venv is untouched:

    /snap/bin/uv run --with transformers --with accelerate --with bitsandbytes --with torch \
        python experiments/vlm-qa-test/run_structured_text_qa.py
    /snap/bin/uv run --with transformers --with accelerate --with bitsandbytes --with torch \
        python experiments/vlm-qa-test/run_structured_text_qa.py --smoke
"""
import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from questions import QUESTIONS  # noqa: E402

MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"

# Per trap question: which engine's parse result to read, and how to render it to text.
# mode "markdown": concatenate blocks in reading order, tables as HTML (what a downstream agent
#   would normally be handed).
# mode "bbox": same, but every block is prefixed with its pixel bbox -- needed for the schematic
#   case where there's no table structure, only spatial proximity between labels and values.
QUESTION_SOURCES = {
    "1b": {"engine": "vl", "mode": "markdown"},
    "8a": {"engine": "pymupdf", "mode": "markdown"},
    "3a": {"engine": "pymupdf", "mode": "bbox"},
}

SKIP_REASONS = {
    "3b": "No text proxy exists for 'which curve sits on top' -- that's pixel-only information "
          "(curve color vs. legend color), not present in any block's text/markdown/html.",
    "5a": "VL timed out (180s) on this doc's pages (all 6, re-run 2026-10-25); PP-OCRv6 line OCR "
          "on this page is garbled (mixed-in CJK artifacts, no correct fraction text) -- no "
          "structured source contains '69 1/8' or anything close to it.",
}


def page_result_path(engine: str, doc: str, page_png: str) -> Path:
    # page_png like "data/pages/ds-lm317/0004.png" -> data/results/<engine>/ds-lm317/0004.json
    page_num = Path(page_png).stem
    return REPO_ROOT / "data" / "results" / engine / doc / f"{page_num}.json"


def render_page_as_text(result_path: Path, mode: str) -> str:
    """Flatten a page's blocks (in reading order) into one text blob: tables as HTML, other
    blocks as markdown/text, optionally bbox-prefixed. This mirrors what a downstream agent
    would actually be handed -- the already-parsed intermediate format, not a re-derived
    summary."""
    data = json.loads(result_path.read_text())
    parts = []
    for block in sorted(data["blocks"], key=lambda b: b["order"]):
        if block["type"] == "table" and block.get("html"):
            content = block["html"]
        elif block.get("markdown"):
            content = block["markdown"]
        elif block.get("text"):
            content = block["text"]
        else:
            continue
        if mode == "bbox":
            x0, y0, x1, y1 = (round(v) for v in block["bbox"])
            parts.append(f"[bbox {x0},{y0},{x1},{y1}] {content}")
        else:
            parts.append(content)
    return "\n\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="run only the first question")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument(
        "--questions", nargs="*", default=list(QUESTION_SOURCES),
        help="question ids to run (default: the 3 trap questions with a usable text source)",
    )
    args = parser.parse_args()

    by_id = {q["id"]: q for q in QUESTIONS}
    qids = args.questions[:1] if args.smoke else args.questions

    import torch
    from transformers import AutoProcessor, BitsAndBytesConfig, Qwen2_5_VLForConditionalGeneration

    quant_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)

    t0 = time.monotonic()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_ID, quantization_config=quant_config, device_map="cuda", dtype=torch.bfloat16,
    )
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    load_time = time.monotonic() - t0
    print(f"loaded {MODEL_ID} in {load_time:.1f}s", file=sys.stderr)

    results = []
    for qid in qids:
        q = by_id[qid]
        if qid in SKIP_REASONS:
            print(f"[{qid}] SKIP -- {SKIP_REASONS[qid]}", file=sys.stderr)
            results.append({"id": qid, "question": q["question"], "answer": None,
                             "skipped": True, "reason": SKIP_REASONS[qid]})
            continue
        source = QUESTION_SOURCES[qid]
        result_path = page_result_path(source["engine"], q["doc"], q["page"])
        if not result_path.exists():
            print(f"[{qid}] SKIP -- no {source['engine']} result at {result_path}", file=sys.stderr)
            results.append({"id": qid, "question": q["question"], "answer": None,
                             "error": f"missing {result_path}"})
            continue

        page_text = render_page_as_text(result_path, source["mode"])
        prompt = (
            "Below is the extracted content of one document page (tables as HTML, other "
            "content as text/markdown). Answer the question using only this content.\n\n"
            f"--- PAGE CONTENT ---\n{page_text}\n--- END PAGE CONTENT ---\n\n"
            f"Question: {q['question']}"
        )
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], return_tensors="pt").to(model.device)

        t0 = time.monotonic()
        with torch.inference_mode():
            out_ids = model.generate(**inputs, max_new_tokens=args.max_new_tokens)
        gen_time = time.monotonic() - t0

        trimmed = out_ids[:, inputs["input_ids"].shape[1]:]
        answer = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()

        print(f"[{qid}] {gen_time:.1f}s -> {answer!r}", file=sys.stderr)
        print(f"[{qid}] ground_truth: {q['ground_truth']!r}", file=sys.stderr)
        results.append({
            "id": qid,
            "question": q["question"],
            "ground_truth": q["ground_truth"],
            "answer": answer,
            "gen_time_s": gen_time,
            "page_text_chars": len(page_text),
            "source_engine": source["engine"],
            "source_mode": source["mode"],
        })

    out_name = "raw_qwen7b_structured_text.smoke.json" if args.smoke else "raw_qwen7b_structured_text.json"
    out_path = Path(__file__).resolve().parent / out_name
    out_path.write_text(json.dumps({"model_variant": MODEL_ID, "load_time_s": load_time,
                                     "results": results}, indent=2))
    print(f"wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
