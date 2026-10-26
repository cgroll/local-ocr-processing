# Multimodal page representation spike

**Not production code.** Tests a richer per-page representation than plain text before building
the real `embedding-search` change: crop every figure/chart/table region as its own image, get a
short *topic-level* description from a local VLM for each (and for tables), and embed
everything -- page text, page image, block images, block descriptions, table content -- with
EmbeddingGemma 2 to check whether it all lands in a sensible, well-aligned shared space.

Last updated: 2026-10-25.

## Why

The embedding-search roadmap item (`openspec/changes`, not yet proposed) assumed plain text
embeddings of the parsed markdown would be the retrieval signal. Before committing to that, the
question was: can we do better by also embedding (a) the page/figure/table *as an image* and (b)
a short, deliberately abstract VLM-written description (topic only, not values -- "a line graph
of efficiency vs. current", not "VIN=5V reaches 92% at 1A") -- and does any of that actually land
where it should in EmbeddingGemma 2's shared 768-dim space, or is it noise?

## Method

Two example pages (`build_rich_page.py`):

- **`ds-lm317` p4** -- table-dominant (one big comparison table, VL already covers this doc).
- **`ds-tps62130` p1** -- figure/chart-dominant (a schematic + an efficiency graph; VL times out
  on this doc, see `experiments/vlm-qa-test/README.md` -- so this is also a test of "can the
  image-embedding route work even when no VLM-based text extraction is available for a page").

For each page: used PP-DocLayoutV3's blocks (`data/results/layout/...`) to find figure/chart/
table regions (bbox), cropped each as its own PNG from the rendered page, and asked
Qwen2.5-VL-7B-Instruct for a one-sentence, explicitly topic-only description per crop (prompt
forbids stating numeric values or reading curves/cells). Tables additionally keep their full
extracted HTML/text content (from VL where available, else pymupdf). Output: one human-readable
Markdown file and one JSON per page (`output/<doc>_<page>.{md,json}`), plus the crop PNGs
(`crops/`).

Then (`embed_rich_page.py`) embedded everything with `google/embeddinggemma-2` (already in the
project's model registry) via `sentence_transformers`: page text and descriptions with
`model.encode(text, prompt_name="Document")`, images (page renders and crops) with
`model.encode(image)` directly (no prefix -- confirmed via the model's own README that prefixes
apply to text only). Then ran four cosine-similarity sanity checks across all 24 embedded items
from both pages together (so cross-document confusion would show up if it existed).

## Results

**Check 1 -- does each description's nearest image (among all 11 images from both pages)
actually match its own crop?** **9/9**, no misses -- including the four small near-duplicate
"generic icon" figures that turned out to be unwanted extras (see "Loose ends" below) and the two
tables from different documents.

**Check 2 -- full description x image similarity matrix.** Own-pair is always the row maximum.
Margins are large for distinctive content (chart: 0.802 own vs. 0.55-0.67 everything else;
schematic: 0.735 own vs. 0.59-0.63 else) and smaller but still correct for genuinely similar
content (the two tables: 0.811/0.739 own vs. 0.625-0.699 cross-table; the four generic icons:
margins as low as 0.77 own vs. 0.68 nearest wrong icon -- expected, they really are visually
similar "symbol on white background" icons).

**Check 3 -- table description vs. its own full HTML content.** 0.853 (LM317) and 0.821
(TPS62130) -- the abstract description stays strongly on-topic with the detailed content it was
abstracted from, without copying its specifics.

**Check 4 -- whole-page image vs. whole-page text, same page should beat cross-page.** Confirmed:
0.690 same-doc vs. 0.618/0.660 cross-doc for one page, 0.837 same-doc vs. 0.660/0.618 cross-doc
for the other.

**Takeaway: the richer representation works as hoped.** Topic-level VLM descriptions, raw image
crops, and full extracted text all land in mutually consistent, correctly-separated positions in
EmbeddingGemma 2's shared space -- across two different documents, for both table-like and
figure/chart-like content, and even when (as for `ds-tps62130`) no VL text extraction exists for
the page at all. This de-risks the plan to use image + description embeddings as first-class
retrieval signals alongside plain text, not just plain text.

## Loose ends (not blocking, but worth fixing before this becomes the real feature)

- **Small marketing icons got swept in as "figures."** PP-DocLayoutV3 doesn't distinguish
  decorative icons from meaningful figures; the `MIN_AREA_PX = 5000` threshold in
  `build_rich_page.py` let four small TI feature icons (ordering/docs/support/design) through on
  `ds-tps62130`. They still embedded and grounded correctly (check 1/2), so they're not a
  correctness problem, just noise that a real pipeline shouldn't pay to describe/embed. Needs a
  smarter filter (aspect ratio, position -- these all sit in the same header strip -- or a
  cheap "is this decorative" classifier) before scaling up.
- **Narrative text assembly is a rough heuristic.** `build_rich_page.py` pairs layout blocks to
  text-source blocks by type+order, best-effort; it inherits pymupdf's known issues (word-wrapped
  text split across lines, the "uF" -> "...F" mangling from `experiments/vlm-qa-test`) and dumps
  some schematic pin-label/value text at the end of the narrative section out of place. Not a
  target of this spike (which was about the image/description embeddings), but a real
  `embedding-search` implementation needs a non-hacky block-to-text join.
- **Only 2 pages, hand-picked.** Enough to validate the mechanism works and to see where it's
  shaky (near-duplicate icons), not enough to know the false-positive/negative rate at scale.
  Scaling to more documents is the natural next step once there's a view on cost (one VLM call
  per visual block, ~0.5-2s each on this hardware -- cheap per page, but 405 pages x several
  blocks each adds up to real minutes, worth batching/budgeting before running broadly).

## Files

- `build_rich_page.py` / `embed_rich_page.py` -- the two scripts, run in that order.
- `output/<doc>_<page>.md` -- human-readable assembled page (read this first).
- `output/<doc>_<page>.json` -- machine-readable version build_rich_page.py produced.
- `output/embedding_check_report.json` -- item list from the embedding run (not the raw vectors).
- `crops/` -- every cropped figure/chart/table image.
