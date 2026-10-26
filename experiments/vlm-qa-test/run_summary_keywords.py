"""Spike: can a local text LLM write a useful summary + keywords for a document, given the
already-extracted markdown/HTML page content (from `docparse.parse --engines vl`)?

Not production code; see experiments/vlm-qa-test/README.md for context. This is a qualitative
check, not a scored benchmark -- there's no ground truth for "good summary". Output is written
to summaries_qwen7b.json for manual read-through.

Uses the same model as `qwen7b` in the main VQA test (Qwen2.5-VL-7B-Instruct, used here as a pure
text model -- no image input) so we're not introducing a new, previously-untested backend.

Run with the ephemeral --with deps so the project venv is untouched:

    /snap/bin/uv run --with transformers --with accelerate --with bitsandbytes --with torch \
        python experiments/vlm-qa-test/run_summary_keywords.py
"""
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"

# The 5 documents the VL engine has already been run on (see top-level README "Stand"), one
# representative page each -- the same pages used as QA test fixtures where available, so the
# qualitative read is against content we've already looked at closely.
DOCS = [
    {"doc": "ds-lm317", "pages": [1, 2, 3, 4]},
    {"doc": "ds-ne555", "pages": [1, 2, 3]},
    {"doc": "bs-dec-08-hrka-d-rk8-schem-dec70", "pages": [1, 4]},
    {"doc": "gd1-001028", "pages": [1]},
    {"doc": "ntrs-19760010918", "pages": [1, 10]},
]

PROMPT_TEMPLATE = """Below is the extracted content of several pages from one document (tables \
as HTML, other content as text/markdown, page breaks marked). Based only on this content:

1. Write a 2-3 sentence summary of what this document is and what it covers.
2. List 8-12 keywords/phrases someone might search for to find this document (mix of specific \
terms -- part numbers, named components, standards -- and general topic words).

Format your answer as:
SUMMARY: <summary>
KEYWORDS: <comma-separated list>

--- DOCUMENT CONTENT ---
{content}
--- END DOCUMENT CONTENT ---
"""


def render_page_as_text(doc: str, page_num: int) -> str | None:
    result_path = REPO_ROOT / "data" / "results" / "vl" / doc / f"{page_num:04d}.json"
    if not result_path.exists():
        return None
    data = json.loads(result_path.read_text())
    parts = []
    for block in sorted(data["blocks"], key=lambda b: b["order"]):
        if block["type"] == "table" and block.get("html"):
            parts.append(block["html"])
        elif block.get("markdown"):
            parts.append(block["markdown"])
        elif block.get("text"):
            parts.append(block["text"])
    return "\n\n".join(parts)


def main():
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
    for entry in DOCS:
        doc = entry["doc"]
        page_texts = []
        for page_num in entry["pages"]:
            text = render_page_as_text(doc, page_num)
            if text:
                page_texts.append(f"[page {page_num}]\n{text}")
        if not page_texts:
            print(f"[{doc}] SKIP -- no VL pages found", file=sys.stderr)
            continue
        content = "\n\n".join(page_texts)
        prompt = PROMPT_TEMPLATE.format(content=content)

        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], return_tensors="pt").to(model.device)

        t0 = time.monotonic()
        with torch.inference_mode():
            out_ids = model.generate(**inputs, max_new_tokens=400)
        gen_time = time.monotonic() - t0

        trimmed = out_ids[:, inputs["input_ids"].shape[1]:]
        answer = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()

        print(f"[{doc}] {gen_time:.1f}s ({len(content)} chars in)\n{answer}\n", file=sys.stderr)
        results.append({
            "doc": doc,
            "pages": entry["pages"],
            "content_chars": len(content),
            "gen_time_s": gen_time,
            "output": answer,
        })

    out_path = Path(__file__).resolve().parent / "summaries_qwen7b.json"
    out_path.write_text(json.dumps({"model_variant": MODEL_ID, "load_time_s": load_time,
                                     "results": results}, indent=2))
    print(f"wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
