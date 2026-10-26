"""Spike: build a richer per-page representation than plain text -- crop out every
figure/chart/table region as its own image, get a short *topic-level* description for each from
a local VLM (not a value dump -- "what kind of thing is this", not "what does it say"), and
assemble everything into one human-readable Markdown file plus a machine-readable JSON.

Not production code. This is step 1 of 2 (see embed_rich_page.py for step 2: turning this into
text/image/description embeddings and sanity-checking that they land where expected in
EmbeddingGemma 2's shared space).

Two example pages, chosen to cover the two regimes we care about:
- ds-lm317 p4: table-dominant (one big comparison table, already has a clean VL HTML table).
- ds-tps62130 p1: figure/chart-dominant (a schematic + an efficiency graph, no table text really
  explains either -- this is exactly the case where image embeddings + descriptions should earn
  their keep over plain text).

Uses PP-DocLayoutV3's blocks (`data/results/layout/...`) to decide *where* to crop -- it's the
project's designated "structure giver" (see top-level README) and gives clean bboxes for
figure/chart/table even when the text-extraction engines don't isolate them the same way.

Run with the ephemeral --with deps so the project venv is untouched:

    /snap/bin/uv run --with transformers --with accelerate --with bitsandbytes --with torch \
        --with pillow python experiments/multimodal-repr-test/build_rich_page.py
"""
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

PAGES = [
    {"doc": "ds-lm317", "page": "0004"},
    {"doc": "ds-tps62130", "page": "0001"},
]

# Layout block types we crop as standalone images + describe. "header_image" (logos) and
# "footer"/"header" text-only regions are skipped -- low value, not what we're testing.
VISUAL_TYPES = {"figure", "chart", "table"}
MIN_AREA_PX = 5000  # skip tiny decorative blocks (e.g. small logos that slip through as "figure")

DESCRIBE_PROMPTS = {
    "table": (
        "Look at this image of a table from a technical document. In exactly one sentence, "
        "describe what the table is about in general terms -- its topic and structure (e.g. "
        "'a comparison of electrical parameters across several product variants, grouped by "
        "output current'). Do NOT state any specific numeric values or name individual rows/"
        "columns verbatim."
    ),
    "figure": (
        "Look at this image from a technical document page. In exactly one sentence, describe "
        "what kind of figure this is (e.g. 'a schematic circuit diagram with an IC and passive "
        "components', 'a photograph of a component package', 'a block diagram of a system'). "
        "Do NOT state specific numeric values, part numbers, or exact readings."
    ),
    "chart": (
        "Look at this image from a technical document page. In exactly one sentence, describe "
        "what kind of chart/graph this is and what it plots in general terms (e.g. 'a line graph "
        "of efficiency versus output current for several input voltages'). Do NOT state specific "
        "numeric values or which curve is highest/lowest."
    ),
}


def load_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def pick_text_source(doc: str, page: str) -> tuple[str, dict]:
    """VL if this page has it (richer markdown/html), else pymupdf."""
    vl = load_json(REPO_ROOT / "data/results/vl" / doc / f"{page}.json")
    if vl and vl.get("status") == "ok" and vl.get("blocks"):
        return "vl", vl
    pymupdf = load_json(REPO_ROOT / "data/results/pymupdf" / doc / f"{page}.json")
    return "pymupdf", pymupdf


def block_text(block: dict) -> str | None:
    if block["type"] == "table" and block.get("html"):
        return block["html"]
    return block.get("markdown") or block.get("text")


def main():
    import torch
    from PIL import Image
    from transformers import AutoProcessor, BitsAndBytesConfig, Qwen2_5_VLForConditionalGeneration

    MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
    quant_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
    t0 = time.monotonic()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_ID, quantization_config=quant_config, device_map="cuda", dtype=torch.bfloat16,
    )
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    print(f"loaded {MODEL_ID} in {time.monotonic()-t0:.1f}s", file=sys.stderr)

    def describe(image: "Image.Image", block_type: str) -> str:
        prompt = DESCRIBE_PROMPTS[block_type]
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image}, {"type": "text", "text": prompt},
        ]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[image], return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out_ids = model.generate(**inputs, max_new_tokens=100)
        trimmed = out_ids[:, inputs["input_ids"].shape[1]:]
        return processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()

    for spec in PAGES:
        doc, page = spec["doc"], spec["page"]
        print(f"\n=== {doc} p{page} ===", file=sys.stderr)
        page_png = REPO_ROOT / "data/pages" / doc / f"{page}.png"
        page_image = Image.open(page_png).convert("RGB")

        layout = load_json(REPO_ROOT / "data/results/layout" / doc / f"{page}.json")
        text_source_name, text_source = pick_text_source(doc, page)
        text_blocks_by_type: dict[str, list[dict]] = {}
        for b in sorted(text_source["blocks"], key=lambda b: b["order"]):
            text_blocks_by_type.setdefault(b["type"], []).append(b)

        narrative_parts = []  # non-visual text, in order, for the "plain text" half of the page
        visual_entries = []  # enriched figure/chart/table entries

        # Layout gives type/box/confidence but no reading order (see top-level README) -- sort
        # top-to-bottom, left-to-right by bbox instead, and use the index in this sorted list as
        # a stand-in "order" for naming/labeling crops.
        layout_blocks_sorted = sorted(layout["blocks"], key=lambda b: (b["bbox"][1], b["bbox"][0]))

        table_idx = {"table": 0}  # which same-typed text block to pair with the Nth layout block
        for position, lb in enumerate(layout_blocks_sorted):
            x0, y0, x1, y1 = lb["bbox"]
            area = (x1 - x0) * (y1 - y0)
            if lb["type"] in VISUAL_TYPES and area >= MIN_AREA_PX:
                crop = page_image.crop((round(x0), round(y0), round(x1), round(y1)))
                crop_name = f"{doc}_{page}_{lb['type']}_{position}.png"
                crop_path = HERE / "crops" / crop_name
                crop.save(crop_path)

                content_text = None
                if lb["type"] == "table":
                    cands = text_blocks_by_type.get("table", [])
                    i = table_idx["table"]
                    if i < len(cands):
                        content_text = block_text(cands[i])
                        table_idx["table"] += 1

                t0 = time.monotonic()
                description = describe(crop, lb["type"])
                print(f"  [{lb['type']} position={position}] {time.monotonic()-t0:.1f}s -> "
                      f"{description!r}", file=sys.stderr)

                visual_entries.append({
                    "type": lb["type"], "label": lb["label"], "bbox": lb["bbox"],
                    "position": position, "crop_path": f"crops/{crop_name}",
                    "description": description, "content_text": content_text,
                })
            elif lb["type"] not in VISUAL_TYPES and lb["type"] not in ("header", "footer"):
                # pull matching narrative text from the text source by type+position, best-effort
                cands = text_blocks_by_type.get(lb["type"], [])
                if cands:
                    t = block_text(cands.pop(0))
                    if t:
                        narrative_parts.append(t)

        # Assemble the human-readable Markdown.
        md = [f"# {doc} -- page {page}", "", f"_text source: {text_source_name}_", ""]
        md.append("## Narrative text")
        md.append("")
        md.extend(narrative_parts)
        md.append("")
        for v in visual_entries:
            md.append(f"## {v['type'].capitalize()}: {v['label']} (position {v['position']})")
            md.append("")
            md.append(f"![{v['label']}]({v['crop_path']})")
            md.append("")
            md.append(f"**Description (VLM, topic-level):** {v['description']}")
            md.append("")
            if v["content_text"]:
                md.append("<details><summary>Full extracted content</summary>")
                md.append("")
                md.append(v["content_text"])
                md.append("")
                md.append("</details>")
                md.append("")

        out_md = HERE / "output" / f"{doc}_{page}.md"
        out_md.write_text("\n".join(md))
        print(f"wrote {out_md}", file=sys.stderr)

        out_json = HERE / "output" / f"{doc}_{page}.json"
        out_json.write_text(json.dumps({
            "doc": doc, "page": page, "page_png": str(page_png.relative_to(REPO_ROOT)),
            "text_source": text_source_name,
            "narrative_text": "\n\n".join(narrative_parts),
            "visual_entries": visual_entries,
        }, indent=2))
        print(f"wrote {out_json}", file=sys.stderr)


if __name__ == "__main__":
    main()
