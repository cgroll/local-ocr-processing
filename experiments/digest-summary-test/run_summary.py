"""Follow-up to experiments/vlm-qa-test/run_summary_keywords.py ("Follow-up C"): that test fed a
local LLM only 1-3 pages of sparse `vl`-markdown per document (vl covered only 5 docs) and found
two failure modes -- keyword generation degenerating into repetition on very thin input (125
chars), and a confidently-wrong summary when page coverage was incomplete. Now that every
document has a full-coverage Markdown digest (`data/results/digest/<doc>.md`, all pages, built
from the reliable pymupdf/ocr + enrichment pipeline, not the sparse `vl`), this re-tests just the
part the user asked for this time: a short title + summary paragraph, nothing else (no keyword
list -- that's exactly the part that broke before).

Reuses the `describe` model already in the registry (Qwen2.5-VL-3B-Instruct) as a plain text
model -- no new model, no new VRAM budget question.

Not production code. Run with:

    /snap/bin/uv run python experiments/digest-summary-test/run_summary.py
"""
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

DOCS = [
    "ds-lm317",  # table-heavy datasheet, good case in the original test too
    "ds-tps62130",  # schematic+chart heavy, no table-only content
    "ntrs-19760010918",  # previously failed due to partial (2/6 page) coverage; digest now has all 6
]

PROMPT_TEMPLATE = """--- DOCUMENT CONTENT (automatically extracted: text, table contents, and \
descriptions of figures/charts) ---
{content}
--- END DOCUMENT CONTENT ---

Based only on the document above: write a short title line, then a 3-5 sentence summary \
paragraph of what this document is and what it covers. Do not list keywords. Format exactly as:
TITLE: <title>
SUMMARY: <paragraph>
"""
# Instructions go AFTER the document, not before: with ~7000+ tokens of document ahead of a
# short instruction, the 3B model's output just trailed off into echoing document fragments
# instead of following the instruction -- a plain prompt-ordering/recency problem, not a model
# or content-quality problem. Confirmed by moving the same instruction to the end: same model,
# same document, correct title+summary output. Keep instructions close to the generation point
# for long-context prompts.


def main():
    from docparse.models import Registry
    from docparse.models.lifecycle import ModelManager

    manager = ModelManager(Registry.load())
    results = []
    try:
        handle = manager.load("describe")
        for doc_id in DOCS:
            digest_path = REPO_ROOT / "data/results/digest" / f"{doc_id}.md"
            content = digest_path.read_text(encoding="utf-8")
            prompt = PROMPT_TEMPLATE.format(content=content)

            messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
            text = handle.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = handle.processor(text=[text], return_tensors="pt").to(handle.model.device)

            import torch
            t0 = time.monotonic()
            with torch.inference_mode():
                out_ids = handle.model.generate(**inputs, max_new_tokens=200)
            gen_time = time.monotonic() - t0
            trimmed = out_ids[:, inputs["input_ids"].shape[1]:]
            output = handle.processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()

            print(f"\n=== {doc_id} ({len(content)} chars in, {gen_time:.1f}s) ===", file=sys.stderr)
            print(output, file=sys.stderr)
            results.append({"doc_id": doc_id, "content_chars": len(content), "gen_time_s": gen_time, "output": output})
    finally:
        manager.unload_all()

    out_path = Path(__file__).resolve().parent / "summaries.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
