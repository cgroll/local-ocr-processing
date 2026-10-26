"""Follow-up to Follow-up A (see README.md): isolate "bad extraction" from "bad local reasoning"
for the two trap questions (8a, 3a) where feeding the local model a *text* representation still
failed -- and where the failure looked like it was caused by the extraction itself (pymupdf
merging all of a table's rows into one cell per column for 8a; pymupdf mangling "uF" to "...F"
for 3a).

This script separates the two steps that `run_structured_text_qa.py` only ever ran together
end-to-end with one source:

1. **Extraction**: ask Gemini 4 Argon (cloud, known from the main QA test to read these pages
   correctly, 20/20) to transcribe -- not answer -- the table/schematic on the page into clean
   text. This is a stand-in for "what would a good extraction pipeline produce", not a claim that
   production should call a cloud VLM for extraction (AGENTS.md: everything runs locally).
2. **Local QA**: feed that clean transcription (no image) to Qwen2.5-VL-7B-Instruct -- the same
   local model used throughout this test directory -- and ask the original question.

If the local model now answers correctly, the bottleneck in Follow-up A was extraction quality,
not the local model's ability to read/reason over structured text. If it's still wrong, the local
model's text-reasoning itself is the limiting factor.

Not production code. Run with the ephemeral --with deps so the project venv is untouched:

    /snap/bin/uv run --with google-genai --with pillow --with transformers --with accelerate \
        --with bitsandbytes --with torch \
        python experiments/vlm-qa-test/run_gemini_extract_then_local_qa.py
"""
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from questions import QUESTIONS  # noqa: E402

GCP_PROJECT = "pi-agent-gemini"
GCP_LOCATION = "global"
GEMINI_MODEL_ID = "gemini-4-argon"
GEMINI_PRICE_IN_PER_MTOK = 2.00
GEMINI_PRICE_OUT_PER_MTOK = 10.00
LOCAL_MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"

TARGETS = [
    {
        "qid": "8a",
        "image": "data/pages/gd1-001147/0001.png",
        "extraction_prompt": (
            "Transcribe the full daily-mean-values data table on this page into clean Markdown. "
            "One row per calendar day (1-31) plus the TOTAL/MEAN/MAX/MIN summary rows at the "
            "bottom -- do not merge multiple days into one cell. Keep all 12 month columns "
            "(OCT..SEP) and all numeric values exactly as printed. Output only the table, no "
            "commentary."
        ),
    },
    {
        "qid": "3a",
        "image": "data/pages/ds-tps62130/0001.png",
        "extraction_prompt": (
            "Look at the 'Typical Application Schematic' on this page. List every passive "
            "component (resistor, capacitor, inductor) visible in it as 'component: value -- "
            "connected to/near pin: <pin label>'. Use the exact pin labels printed next to the "
            "IC (e.g. PVIN, AVIN, EN, SW, VOS, PG, FB, AGND, PGND). Use correct unit symbols "
            "(uF for microfarad, nF for nanofarad, uH for microhenry, k for kilohm) -- do not "
            "substitute other characters for Greek letters. Output only the list, no commentary."
        ),
    },
]


def gemini_extract(client, types, image_path: Path, prompt: str) -> dict:
    img_bytes = image_path.read_bytes()
    t0 = time.monotonic()
    resp = None
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL_ID,
                contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/png"), prompt],
            )
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  extraction attempt {attempt} failed after {time.monotonic()-t0:.1f}s: {e!r}",
                  file=sys.stderr)
    gen_time = time.monotonic() - t0
    if resp is None:
        return {"text": None, "error": repr(last_err), "gen_time_s": gen_time}
    usage = resp.usage_metadata
    in_tok = usage.prompt_token_count or 0
    out_tok = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
    cost = (in_tok / 1_000_000) * GEMINI_PRICE_IN_PER_MTOK + \
           (out_tok / 1_000_000) * GEMINI_PRICE_OUT_PER_MTOK
    return {
        "text": (resp.text or "").strip(), "gen_time_s": gen_time,
        "input_tokens": in_tok, "output_tokens": out_tok, "cost_usd": cost,
    }


def main():
    by_id = {q["id"]: q for q in QUESTIONS}

    # Step 1: extraction (Gemini Argon, cloud, no GPU involved).
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION,
        http_options=types.HttpOptions(timeout=60_000),
    )

    extractions = {}
    for t in TARGETS:
        print(f"[{t['qid']}] extracting via {GEMINI_MODEL_ID}...", file=sys.stderr)
        result = gemini_extract(client, types, REPO_ROOT / t["image"], t["extraction_prompt"])
        extractions[t["qid"]] = result
        print(f"[{t['qid']}] extraction ({result.get('gen_time_s', 0):.1f}s, "
              f"${result.get('cost_usd', 0):.5f}):\n{result.get('text')}\n", file=sys.stderr)

    # Step 2: local QA over the clean extraction (Qwen2.5-VL-7B, text-only, no image).
    import torch
    from transformers import AutoProcessor, BitsAndBytesConfig, Qwen2_5_VLForConditionalGeneration

    quant_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
    t0 = time.monotonic()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        LOCAL_MODEL_ID, quantization_config=quant_config, device_map="cuda", dtype=torch.bfloat16,
    )
    processor = AutoProcessor.from_pretrained(LOCAL_MODEL_ID)
    load_time = time.monotonic() - t0
    print(f"loaded {LOCAL_MODEL_ID} in {load_time:.1f}s", file=sys.stderr)

    results = []
    for t in TARGETS:
        qid = t["qid"]
        q = by_id[qid]
        extraction = extractions[qid]
        if not extraction.get("text"):
            print(f"[{qid}] SKIP local QA -- extraction failed: {extraction.get('error')}",
                  file=sys.stderr)
            results.append({"id": qid, "extraction": extraction, "local_answer": None})
            continue

        prompt = (
            "Below is a clean transcription of one document page's relevant content. Answer "
            "the question using only this content.\n\n"
            f"--- PAGE CONTENT ---\n{extraction['text']}\n--- END PAGE CONTENT ---\n\n"
            f"Question: {q['question']}"
        )
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], return_tensors="pt").to(model.device)

        t0 = time.monotonic()
        with torch.inference_mode():
            out_ids = model.generate(**inputs, max_new_tokens=256)
        gen_time = time.monotonic() - t0

        trimmed = out_ids[:, inputs["input_ids"].shape[1]:]
        answer = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()

        print(f"[{qid}] local answer ({gen_time:.1f}s): {answer!r}", file=sys.stderr)
        print(f"[{qid}] ground_truth: {q['ground_truth']!r}", file=sys.stderr)
        results.append({
            "id": qid,
            "question": q["question"],
            "ground_truth": q["ground_truth"],
            "extraction": extraction,
            "local_answer": answer,
            "local_gen_time_s": gen_time,
        })

    out_path = Path(__file__).resolve().parent / "raw_gemini_extract_then_qwen7b.json"
    out_path.write_text(json.dumps({
        "extraction_model": GEMINI_MODEL_ID,
        "local_model": LOCAL_MODEL_ID,
        "local_load_time_s": load_time,
        "results": results,
    }, indent=2))
    print(f"wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
