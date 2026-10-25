"""Informal VLM QA test - generic HF causal-VLM backend (Qwen2.5-VL / Gemma-3), 4-bit bnb.

Not production code; see experiments/vlm-qa-test/README for context. Run with the ephemeral
--with deps so the project venv (pinned transformers etc.) is untouched, e.g.:

    /snap/bin/uv run --with transformers --with accelerate --with bitsandbytes --with pillow \
        python experiments/vlm-qa-test/run_hf_vlm.py --model qwen7b --smoke
    /snap/bin/uv run --with transformers --with accelerate --with bitsandbytes --with pillow \
        python experiments/vlm-qa-test/run_hf_vlm.py --model qwen3b
    /snap/bin/uv run --with transformers --with accelerate --with bitsandbytes --with pillow \
        python experiments/vlm-qa-test/run_hf_vlm.py --model gemma

--smoke runs only the first question to fail fast before burning time on the full 20.
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from questions import QUESTIONS  # noqa: E402

MODEL_IDS = {
    "qwen7b": "Qwen/Qwen2.5-VL-7B-Instruct",
    "qwen3b": "Qwen/Qwen2.5-VL-3B-Instruct",
    "gemma": "google/gemma-3-4b-it",
}


def nvidia_smi_used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(out.splitlines()[0])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=list(MODEL_IDS.keys()))
    parser.add_argument("--smoke", action="store_true", help="run only the first question")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()

    model_id = MODEL_IDS[args.model]
    questions = QUESTIONS[:1] if args.smoke else QUESTIONS

    import torch
    from PIL import Image
    from transformers import AutoProcessor, BitsAndBytesConfig

    quant_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)

    vram_before = nvidia_smi_used_mib()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.monotonic()

    if args.model.startswith("qwen"):
        from transformers import Qwen2_5_VLForConditionalGeneration
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_id, quantization_config=quant_config, device_map="cuda", dtype=torch.bfloat16,
        )
    else:
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(
            model_id, quantization_config=quant_config, device_map="cuda", dtype=torch.bfloat16,
        )
    processor = AutoProcessor.from_pretrained(model_id)
    load_time = time.monotonic() - t0
    print(f"[{args.model}] loaded {model_id} in {load_time:.1f}s, vram_before={vram_before} MiB",
          file=sys.stderr)

    results = []
    gen_times = []
    for q in questions:
        img_path = REPO_ROOT / q["page"]
        image = Image.open(img_path).convert("RGB")
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": q["question"]},
        ]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[image], return_tensors="pt").to(model.device)

        t0 = time.monotonic()
        with torch.inference_mode():
            out_ids = model.generate(**inputs, max_new_tokens=args.max_new_tokens)
        gen_time = time.monotonic() - t0
        gen_times.append(gen_time)

        trimmed = out_ids[:, inputs["input_ids"].shape[1]:]
        answer = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()

        print(f"[{args.model}] {q['id']}: {gen_time:.1f}s -> {answer!r}", file=sys.stderr)
        results.append({
            "id": q["id"],
            "question": q["question"],
            "answer": answer,
            "gen_time_s": gen_time,
        })

    vram_peak_torch = torch.cuda.max_memory_allocated() / (1024 ** 2)
    vram_peak_smi = nvidia_smi_used_mib()

    summary = {
        "backend": args.model,
        "model_variant": model_id,
        "quantization": "4-bit bnb (bnb_4bit_compute_dtype=bfloat16)",
        "load_time_s": load_time,
        "gen_times_s": gen_times,
        "gen_time_mean_s": statistics.mean(gen_times) if gen_times else None,
        "gen_time_median_s": statistics.median(gen_times) if gen_times else None,
        "vram_peak_torch_mib": vram_peak_torch,
        "vram_peak_nvidia_smi_mib": vram_peak_smi,
        "vram_before_mib": vram_before,
        "results": results,
    }

    out_name = f"raw_{args.model}.smoke.json" if args.smoke else f"raw_{args.model}.json"
    out_path = Path(__file__).resolve().parent / out_name
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"[{args.model}] wrote {out_path}", file=sys.stderr)
    print(f"[{args.model}] load={load_time:.1f}s mean_gen={summary['gen_time_mean_s']:.1f}s "
          f"vram_peak_smi={vram_peak_smi}MiB vram_peak_torch={vram_peak_torch:.0f}MiB", file=sys.stderr)


if __name__ == "__main__":
    main()
