"""Step 2 of the multimodal representation spike (see build_rich_page.py for step 1): embed
everything build_rich_page.py produced -- the page's narrative text, each visual block's image
crop, each visual block's short VLM description, and (for tables) the full extracted content --
with EmbeddingGemma 2, and sanity-check that related things land close together in its shared
768-dim space while unrelated things don't.

Not production code. This does not answer "is retrieval good" (that needs real queries, see the
embedding-search / retrieval-eval roadmap items) -- it answers the narrower question asked right
before this: "does the richer representation (image embeddings + topic-level descriptions, not
just raw text) actually produce a sensible, well-aligned embedding space to build that on?"

Run with the ephemeral --with deps so the project venv is untouched:

    /snap/bin/uv run --with sentence-transformers --with torch --with pillow \
        python experiments/multimodal-repr-test/embed_rich_page.py
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

PAGES = [("ds-lm317", "0004"), ("ds-tps62130", "0001")]


def cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def main():
    import torch
    from PIL import Image
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        "google/embeddinggemma-2", device="cuda",
        config_kwargs={"audio_config": None}, model_kwargs={"dtype": torch.bfloat16},
    )

    items = []  # flat list of every embeddable thing, across both pages
    for doc, page in PAGES:
        data = json.loads((HERE / "output" / f"{doc}_{page}.json").read_text())

        page_image = Image.open(REPO_ROOT / data["page_png"]).convert("RGB")
        items.append({
            "key": f"{doc}/p{page}/PAGE_IMAGE", "doc": doc, "kind": "page_image",
            "embedding": model.encode(page_image),
        })
        items.append({
            "key": f"{doc}/p{page}/PAGE_TEXT", "doc": doc, "kind": "page_text",
            "embedding": model.encode(data["narrative_text"][:4000], prompt_name="Document"),
        })

        for v in data["visual_entries"]:
            label = f"{doc}/p{page}/{v['type']}_{v['position']}_{v['label']}"
            crop = Image.open(HERE / v["crop_path"]).convert("RGB")
            items.append({"key": f"{label}/IMAGE", "doc": doc, "kind": "visual_image",
                          "embedding": model.encode(crop)})
            items.append({"key": f"{label}/DESC", "doc": doc, "kind": "visual_desc",
                          "embedding": model.encode(v["description"], prompt_name="Document")})
            if v.get("content_text"):
                items.append({
                    "key": f"{label}/CONTENT", "doc": doc, "kind": "visual_content",
                    "embedding": model.encode(v["content_text"][:2000], prompt_name="Document"),
                })

    print(f"\nEmbedded {len(items)} items.\n", file=sys.stderr)

    # --- Sanity check 1: cross-modal grounding. For every visual block that has both an IMAGE
    # and a DESC embedding, is DESC's nearest IMAGE (among ALL images, both pages) its own? ---
    image_items = [it for it in items if it["kind"] in ("visual_image", "page_image")]
    print("=== Check 1: does each description's nearest image match its own crop? ===",
          file=sys.stderr)
    n_right = 0
    desc_items = [it for it in items if it["kind"] == "visual_desc"]
    for d in desc_items:
        own_key = d["key"].replace("/DESC", "/IMAGE")
        sims = [(cos(d["embedding"], im["embedding"]), im["key"]) for im in image_items]
        sims.sort(reverse=True)
        best_sim, best_key = sims[0]
        correct = best_key == own_key
        n_right += correct
        mark = "OK" if correct else "MISS"
        print(f"  [{mark}] {d['key']:55s} nearest image: {best_key} (sim={best_sim:.3f})",
              file=sys.stderr)
    print(f"  {n_right}/{len(desc_items)} descriptions' nearest image was their own crop.\n",
          file=sys.stderr)

    # --- Sanity check 2: do same-topic items from DIFFERENT pages still separate correctly?
    # e.g. the TPS62130 chart's description should sit closer to the TPS62130 chart's own image
    # than to the LM317 table's image, and vice versa for distinguishing table vs. chart/figure. ---
    print("=== Check 2: full description x image similarity matrix ===", file=sys.stderr)
    header = "".join(f"{im['key'][-28:]:>30s}" for im in image_items)
    print(" " * 45 + header, file=sys.stderr)
    for d in desc_items:
        row = "".join(f"{cos(d['embedding'], im['embedding']):30.3f}" for im in image_items)
        print(f"{d['key'][-43:]:45s}{row}", file=sys.stderr)

    # --- Sanity check 3: for tables, does the short topic-level DESC embedding sit reasonably
    # close to the full CONTENT (HTML) embedding of the same table? (same topic, different
    # specificity -- expect positive but not necessarily top-1 correlation) ---
    print("\n=== Check 3: table description vs. own full content text ===", file=sys.stderr)
    content_items = [it for it in items if it["kind"] == "visual_content"]
    for c in content_items:
        own_desc_key = c["key"].replace("/CONTENT", "/DESC")
        own_desc = next((d for d in desc_items if d["key"] == own_desc_key), None)
        if own_desc:
            print(f"  {c['key']:55s} vs own DESC: {cos(c['embedding'], own_desc['embedding']):.3f}",
                  file=sys.stderr)

    # --- Sanity check 4: whole-page image vs whole-page text, same page should beat cross-page ---
    print("\n=== Check 4: page image vs. page text, same-page vs. cross-page ===", file=sys.stderr)
    page_images = [it for it in items if it["kind"] == "page_image"]
    page_texts = [it for it in items if it["kind"] == "page_text"]
    for pt in page_texts:
        for pi in page_images:
            same = pt["doc"] == pi["doc"]
            print(f"  {pt['key']:30s} vs {pi['key']:30s} ({'same' if same else 'cross'}-doc): "
                  f"{cos(pt['embedding'], pi['embedding']):.3f}", file=sys.stderr)

    out_path = HERE / "output" / "embedding_check_report.json"
    out_path.write_text(json.dumps({
        "n_items": len(items),
        "check1_desc_to_own_image_hit_rate": n_right / len(desc_items) if desc_items else None,
        "items": [{"key": it["key"], "doc": it["doc"], "kind": it["kind"]} for it in items],
    }, indent=2))
    print(f"\nwrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
