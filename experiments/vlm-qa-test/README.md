# Informal VLM QA test

**Not production code.** This is a one-off, hand-run comparison of vision-language models for
answering questions about scanned document pages (datasheets, old government reports, NASA
papers, a DEC hardware manual). It exists to get a gut feeling for which VLM backend(s) would be
worth building real `src/docparse` support for. Nothing here is wired into the production
pipeline. The page images it references (`data/pages/...`) live under `data/`, which is
deliberately git-ignored project-wide (see the top-level README) -- so this directory is
committed for the code/results/writeup, but reproducing the report view requires `data/` to be
present locally (same as the existing `docparse.viewer` tool already assumes).

Last updated: 2026-10-25.

## Goal

Answer, for a handful of real scanned pages with known ground truth: how good are today's VLMs
(local, open-weight vs. a cloud flagship) at pulling specific facts out of dense technical
tables, graphs, and dimensioned drawings? And: what does the cloud option actually cost per
question?

## What to read if you're picking this back up later

- **`combined_results.json`** -- the single joined file: every question, its page path, ground
  truth, and every backend's answer + verdict + note + timing/cost, side by side. This is what a
  future visual report (HTML page, notebook, whatever) should load -- it should not need to
  re-parse `questions.py` / `raw_*.json` / `judgments.py` itself. Regenerate it after adding a
  backend or editing a verdict:
  ```
  /snap/bin/uv run python experiments/vlm-qa-test/build_combined.py
  ```
- **`questions.py`** -- the 20 questions (10 documents x 2 questions each), each with `id`,
  `doc`, `page` (path to the page PNG, relative to repo root), `question`, `ground_truth`.
  `ground_truth` was filled in by hand reading the page and was itself re-verified against the
  page image during judging (see "Ground truth corrections" below -- it was right every time a
  model's answer was checked against it).
- **`judgments.py`** -- hand-filled verdicts (`correct` / `partial` / `wrong` + a one-line note)
  per question per backend, written after reading each page image and comparing it against each
  backend's raw answer.
- **`raw_<backend>.json`** -- one file per backend, written by that backend's `run_*.py` script.
  Each has per-question answers + timing, and for the Gemini backends, per-question token counts
  and cost.
- **`run_structured_text_qa.py`** / **`raw_qwen7b_structured_text.json`** and
  **`run_summary_keywords.py`** / **`summaries_qwen7b.json`** -- two follow-up spikes (see
  "Follow-up A" and "Follow-up C" below): does text extraction instead of pixels fix the trap
  questions, and can a local LLM write useful doc summaries/keywords. Not joined into
  `combined_results.json` -- small enough to read as-is.

## The 10 source documents

Picked to span different kinds of "hard to OCR-naively" content: dense parametric tables with
near-duplicate columns (LM317, NE555, IRF540 datasheets), a graph that has to be read visually
(TPS62130 efficiency curves), old mechanical drawings with handwritten-style fraction dimensions
(DEC PDP-8 interface manual), a wiring table (NASA F2 Logic sheet), a disk-drive schematic
contents page (DEC RK01/RK08 manual), a plain data table (USGS stream gage report), and two
"soft" questions about a report cover (title + open-ended photo description, California grape
acreage report) and an abstract (NASA conference paper).

## Backends tested

| Backend | Model | Where it runs | Script |
|---|---|---|---|
| `qwen3b` | Qwen2.5-VL-3B-Instruct | local GPU, 4-bit bnb | `run_hf_vlm.py --model qwen3b` |
| `qwen7b` | Qwen2.5-VL-7B-Instruct | local GPU, 4-bit bnb | `run_hf_vlm.py --model qwen7b` |
| `gemma` | google/gemma-3-4b-it | local GPU, 4-bit bnb | `run_hf_vlm.py --model gemma` |
| `paddle_vl` | PaddleOCR-VL-1.6-0.9B | local GPU | `run_paddle_vl.py` |
| `gemini_argon` | Gemini 4 Argon (Google flagship, GA since 2026-10-13) | Vertex AI (cloud) | `run_gemini_vl.py --model argon` |

Also smoke-tested but not run to completion: **Gemini 3.1 Pro** (`gemini-3.1-pro-preview`,
`run_gemini_vl.py --model pro31`) -- see "Gemini cost" below for why we stopped at the smoke
test.

All `run_*.py` scripts are meant to be invoked with ephemeral `uv run --with <deps>` so the
project's pinned venv is never touched -- see each script's module docstring for the exact
command.

## Results

20/20 questions, verdicts from `judgments.py` (verified by hand against each page image):

| Backend | correct | partial | wrong |
|---|---|---|---|
| **Gemini 4 Argon** | **20** | 0 | 0 |
| Qwen2.5-VL-3B | 15 | 0 | 5 |
| Qwen2.5-VL-7B | 14 | 1 | 5 |
| Gemma-3-4b-it | 8 | 2 | 10 |
| PaddleOCR-VL-1.6 | 5 | 0 | 15 |

**Gemini 4 Argon got every question right**, including all five "trap" questions below that
every local model missed at least one of.

### The five questions where multiple/all local models failed together

These are the interesting ones -- not a single model being weak, but a *class* of error that hit
several models the same way:

- **1b** (LM317HV operating temp @ 1.5A): the comparison table has a `-40 to 125°C` value in the
  adjacent LM317A column at the same row. qwen7b and gemma both picked that up instead of
  LM317HV's actual `0 to 125°C` -- a column-alignment slip in a dense table.
- **3a** (output capacitor value in a schematic): qwen3b said 100µF (a value that doesn't appear
  anywhere on the page -- outright hallucination); gemma said 0.1µF (picked the wrong capacitor
  in the schematic -- the AVIN decoupling cap, not the output cap). Only qwen7b and argon got
  22µF right.
- **3b** (which input-voltage curve has the highest efficiency): all three local VLMs picked the
  wrong curve (17V or 12V instead of 5V) reading the efficiency-vs-current graph. This is a
  genuine visual-reasoning task (matching an arrow/label to a curve by color/position), and all
  three failed it the same way.
- **5a** (PDP-8 cabinet height, `69 1/8"` on the drawing): qwen3b said 69⅜, qwen7b and gemma both
  said 69⅝. All three misread the same small handwritten-style fraction.
- **8a** (max JAN discharge value in a daily-values table): qwen3b, qwen7b, and gemma each picked
  a *different* wrong number from the table (147, 1810, 1760) instead of reading the `MAX` summary
  row (5730). All three grabbed some individual daily value instead of the aggregate.

Takeaway: dense tables with near-duplicate neighboring columns/rows, and graphs that require
matching a legend to a curve, are a real weak spot for all four of the smaller/local models
tested -- not model-specific quirks.

## Follow-up A: structured text instead of pixels, on the trap questions

**Question:** the 5 trap questions above are mostly dense-table column/row mix-ups and a
curve-to-legend mismatch. Does handing the model the *already-extracted* structured
markdown/HTML (what `src/docparse` actually produces) instead of the raw page image fix this --
i.e. is the problem "the model can't visually parse a dense table" rather than "the model can't
reason about a dense table"? `run_structured_text_qa.py`, same model (Qwen2.5-VL-7B), same
questions, text-only input (no image).

**Not all 5 trap questions had a usable structured source to test with**, which is itself a
finding (re-run 2026-10-25):

- **1b** (ds-lm317): VL had already been run for this doc -- clean HTML table available.
- **8a** (gd1-001147): VL had not been run for this doc; ran it specifically for this test and it
  **timed out on all 6 pages** (`PageTimeout: inference exceeded the limit of 180 s`) -- not a
  harness artifact this time, the production `docparse.parse --engines vl` path itself hit the
  180s cap. Fell back to pymupdf's table extraction instead (native PDF, so pymupdf has a real
  text layer).
- **3a** (ds-tps62130): VL also timed out on all 6 pages of this doc. Fell back to pymupdf's raw
  positioned text blocks (bbox + text -- a schematic isn't a table, so there's no HTML table to
  fall back to, only spatial proximity between labels and values).
- **3b** and **5a** were skipped outright, not run with degraded input: 3b (which curve sits on
  top) has no text proxy at all -- that's pixel-only information (curve color vs. legend color).
  5a's VL run timed out too, and PP-OCRv6's line OCR on that scanned page is too garbled (mixed-in
  CJK artifacts, no correct fraction text) to contain "69 1/8" or anything close. Feeding the
  model garbled or absent text would not have been a fair test.

**Result: 1 of 3 fixed, and the other 2 failed for reasons that are not "vision vs. text":**

| Q | Source | Model's answer | Ground truth | Verdict |
|---|---|---|---|---|
| 1b | VL HTML table | "0°C to 125°C" | 0 to 125 °C | **correct** -- the column mix-up (LM317A's -40 to 125 at the same row) is gone once the columns are named cells instead of visually adjacent pixels. |
| 8a | pymupdf HTML table | "143 cfs" | 5730 | **wrong**, and wrong the *same way* as before: 143 is JAN day 4's actual daily value, not the MAX summary row. pymupdf's table reconstruction stacks all ~31 day-values plus TOTAL/MEAN/MAX/MIN into one newline-joined blob per `<td>`, with no per-row `<tr>` -- so the "text" table has the exact same row-identification ambiguity a human (or a VLM reading pixels) would have reading a cramped printed table. Giving the model text didn't help because the *extraction*, not the modality, lost the row structure. |
| 3a | pymupdf bbox + text | "3.3 nF" | 22 uF | **wrong**. The correct block (`[bbox 519,1230,589,1247] "100 k⏎22 …F"`) sits at the same y-range as the `VOS` pin label, so the bbox proximity needed to answer this is present in the prompt -- the model didn't use it, and may also have been thrown by pymupdf mangling "µF" to "…F" (a real encoding bug in the extraction, not a model problem) and picking the nearest *cleanly-formatted* number instead. |

**Takeaway:** "give the model text instead of pixels" only pays off when the text extraction
itself preserves the structure that matters (1b). When the extraction is lossy in the same way
the visual layout is ambiguous (8a's merged table rows) or spatial reasoning isn't actually used
by the model despite being available (3a), reformatting as text doesn't help -- and can introduce
*new* failure modes (encoding corruption). This matches the existing README note that
PaddleOCR-VL's low score was "partly an artifact of the harness": extraction quality, not
modality, is turning out to be the recurring bottleneck. It also surfaces a concrete pipeline gap
worth fixing before `embedding-search`/`retrieval-eval`: pymupdf's table block builder needs
proper per-row `<tr>` reconstruction (not newline-stacked cells) and correct Unicode handling
(µ), or any text-based reader will inherit the same errors a pixel-based one makes.

Also notable: VL timed out on *every single page* of both additional docs tried (12 pages, all at
exactly the 180s cap) -- not an occasional outlier as the top-level README describes ("selten...
meist nicht reproduzierbar"), but a total failure for these two documents specifically (a
multi-net schematic+graph page and a dense numeric table report). Worth a closer look before
relying on VL coverage for routing decisions.

### Follow-up A2: is it the extraction or the local model's reasoning?

Follow-up A left 8a and 3a wrong, and both looked like they could be explained by lossy
extraction (pymupdf's merged table rows for 8a, pymupdf's "uF"->"...F" mangling for 3a) rather
than the local model's reasoning. `run_gemini_extract_then_local_qa.py` tests this directly: ask
Gemini 4 Argon to **transcribe** (not answer) the table/schematic into clean text, then feed that
clean text -- no image -- to the same local Qwen2.5-VL-7B used throughout. If the local model
gets it right now, extraction was the bottleneck; if not, the local model's own text reasoning is
the limit. Cost: $0.029 total for both extractions.

| Q | Clean (Gemini) extraction | Local model's answer on the clean text | Verdict |
|---|---|---|---|
| 3a | `capacitor: 22 uF -- connected to/near pin: VOS, SW` (correct unit, explicit pin pairing) | "22 uF" | **correct** -- confirms extraction (not reasoning) was the bottleneck for this one. Fixing pymupdf's unit-mangling and adding explicit label-to-value pairing would likely fix this class on real data too. |
| 8a | A fully clean, properly row-separated Markdown table, explicit `MAX` row: `\| MAX \| 749 \| 221 \| 221 \| 5730 \| ...`| "1166 cubic feet per second" | **still wrong** -- and tellingly, 1166 is the **MEAN** row for JAN, not MAX. The model progressed from "grabs a random daily value" (Follow-up A, pymupdf source) to "grabs the wrong *summary* row" (clean source) -- but a perfectly clean, explicitly labeled table still isn't enough. This one is a genuine local-model text-reasoning limit, not an extraction artifact. |

**Takeaway:** the two trap questions split cleanly into different root causes once extraction
quality is controlled for. This matters for where to invest: 3a's failure mode (lossy/garbled
extraction) is a pipeline problem worth fixing in `pymupdf`'s adapter (Unicode handling, explicit
label-value pairing for schematics). 8a's failure mode (confusing adjacent summary-row labels in
a dense table even when the text is unambiguous) is a 7B-model reasoning ceiling that better
extraction cannot buy back -- that's either a job for a bigger/better local model, a verification
step (e.g. asking the model to quote the exact row label it used), or routing this kind of
question to a stronger backend.

Raw output: `raw_gemini_extract_then_qwen7b.json`.

## Follow-up C: can a local LLM write document summaries and keywords?

**Question:** for the embedding-search / retrieval-eval roadmap, could a local text LLM generate
doc-level summaries and keywords as extra retrieval metadata? `run_summary_keywords.py`, same
model (Qwen2.5-VL-7B, text-only), fed the concatenated VL-extracted markdown of a few pages per
document, for the 5 docs where VL output already exists, asked for a 2-3 sentence summary plus
8-12 keywords.

| Doc | Pages used | Input size | Summary quality | Keyword count | Keyword quality |
|---|---|---|---|---|---|
| ds-lm317 | 1-4 | 7.8k chars | accurate, on-topic | ~55 (asked for 8-12) | mostly on-topic but way over length, some filler |
| ds-ne555 | 1-3 | 6.0k chars | accurate, on-topic | ~24 | good, mostly specific terms |
| bs-dec-08-... | 1, 4 | 5.1k chars | accurate, on-topic | ~20 | good, specific part/drawing names |
| gd1-001028 | 1 only | **125 chars** | accurate for what little text exists | **~90, degenerate repetition** | breaks down into a runaway loop ("agricultural policy X" repeated dozens of times with X cycling through near-synonyms) |
| ntrs-19760010918 | 1, 10 | 1.6k chars | accurate **but scoped to page 10 only** (page 1 has no VL result) -- describes the doc as "a wiring diagram" when it's actually a NASA technical report that happens to contain one | 15 | reasonable, but narrow for the same reason |

**Takeaway:** when there's enough real content, the 7B model writes genuinely good, accurate
summaries and mostly-sensible keywords -- promising for metadata enrichment. But two failure
modes showed up that any production use needs to guard against:

1. **Instruction-following on count collapses under both too-much and too-little input.**
   With plenty of input (ds-lm317) the model way overshoots the requested keyword count instead
   of stopping. With almost no input (gd1-001028's 125-char cover page) it doesn't say "not
   enough information" -- it fills the token budget with repetitive, increasingly generic
   hallucinated keywords. Needs a minimum-input-length gate and/or a hard keyword-count cap with
   post-hoc truncation/dedup, not just a prompt instruction.
2. **Missing pages silently narrow the summary's scope with no error signal.** `ntrs-19760010918`
   only had VL output for 1 of its pages in this sample set; the model summarized confidently as
   if that page were the whole document. For retrieval metadata this is dangerous -- an
   authoritative-sounding but incomplete summary is worse than no summary, because nothing flags
   it as partial. Any doc-level summary step needs to know (and probably state) its own page
   coverage.

Raw outputs: `raw_qwen7b_structured_text.json`, `summaries_qwen7b.json`.

### PaddleOCR-VL's low score is partly an artifact of this harness

PaddleOCR-VL's poor score (5/20) is not a fair read of the underlying model's QA ability. It had
to be capped at `max_new_tokens=100` (see "Bugs found" below), so most of its "answers" are just
whatever the page's raw OCR dump happened to contain in the first ~100 tokens -- often the page
header/features section, cut off before reaching the actually-relevant table or paragraph. This
harness bypasses PaddleOCR-VL's normal structured-parsing pipeline (the one `src/docparse`
actually uses) in favor of its lower-level direct-QA `DocVLM.predict()` path, which is not what
it's designed/tuned for.

## Gemini cost

Tracked directly from each API response's `usage_metadata` (real billed token counts), not
estimated:

| Model | Price (in/out per 1M tok) | Mean tokens/question | Mean cost/question | Cost per 1000 questions | Mean latency/question |
|---|---|---|---|---|---|
| Gemini 4 Argon | $2.00 / $10.00 | 1151 in / 55 out | $0.00285 | **~$2.85** | 11.2s (one 49.7s outlier) |
| Gemini 3.1 Pro | $2.00 / $12.00 | 1132 in / 948 out* | $0.01364 | ~$13.64 | 10.3s |

\* Gemini 3.1 Pro's output-token count is dominated by internal reasoning ("thinking") tokens
(948 of ~950 total on the one question tested) -- Vertex bills those as output tokens. That's
why it costs ~5x more per question despite similar per-token pricing: it's generating far more
(mostly invisible) tokens to answer the same question. We only ran a 1-question smoke test on
3.1 Pro for this reason -- the full 20-question Argon run already showed Argon matching or
beating every local backend on accuracy at a fraction of 3.1 Pro's cost, so there was no point
spending 5x more to test the "older/pricier" Pro tier across all 20 questions.

The full 20-question Gemini 4 Argon run cost **$0.057 total**.

## Bugs found and fixed along the way

Two real infrastructure bugs got found and fixed while building this out (both still fixed in
the current scripts, not just worked around for one run):

1. **PaddleOCR-VL GPU allocator hang** (`_paddle_one_question.py`): `model.predict()` would hang
   indefinitely -- 0% GPU utilization, one CPU core pegged at 100%+, no error, no timeout, every
   single call, independent of `max_new_tokens` (reproduced down to `max_new_tokens=5`) and
   independent of CPU-vs-GPU device. Root cause: PaddlePaddle's default `auto_growth` VRAM
   allocator gets stuck in an infinite `ioctl` retry loop against the NVIDIA kernel module on
   this GPU/driver combo -- a known bug,
   [PaddleOCR#17693](https://github.com/PaddlePaddle/PaddleOCR/issues/17693). Fix:
   `FLAGS_allocator_strategy=naive_best_fit` set before paddle is imported. Also replaced the
   original in-process `SIGALRM` watchdog (which could not interrupt the hang -- it's blocked in
   a GIL-held C call) with a per-question OS subprocess under a hard `timeout` command
   (`run_paddle_vl.py` orchestrates, `_paddle_one_question.py` does one question per process).

2. **Gemini client hang on a stalled connection** (`run_gemini_vl.py`): the default
   `google-genai` `Client` has no request timeout. Hit a real 12+ minute hang on question 8b of
   the first full Argon run -- confirmed via `/proc/<pid>/status` and `ss -tnp` that the process
   was genuinely blocked in `wait_woken` on an established TCP connection to a Google IP, not
   spinning or retrying. Fix: `http_options=types.HttpOptions(timeout=60_000)` on the client,
   plus a 3-attempt retry loop with visible per-attempt logging around each
   `generate_content()` call, so a stalled call surfaces (and gets retried) within a bounded
   time instead of blocking the whole run silently forever.

## Auth / GCP setup (for the Gemini backend)

Uses the same GCP project speech-to-speech's `config.py` already documents:

- **Project:** `pi-agent-gemini`
- **Account:** `[redacted-gmail-account]`
- **Auth:** Application Default Credentials (`~/.config/gcloud/application_default_credentials.json`)
  -- plain Gemini-Developer-API keys are blocked by this project's org policy
  (`API_KEY_SERVICE_BLOCKED`), so it has to go through Vertex AI with ADC. `gcloud` CLI doesn't
  need to be on `PATH` for this to work -- the ADC file's stored `refresh_token` is enough for
  `google-genai`'s auth layer to refresh tokens itself.
- **Location:** `global` -- **not** `us-central1`. Google's docs list `us-central1` as supported
  for both Gemini 4 Argon and Gemini 3.1 Pro, but it 404s in practice for this project
  (`Publisher model ... was not found`); `global` works for both models.

## Future report (not built yet)

The ask this was captured for: eventually build an actual readable report -- per question, show
the page image, the question, the ground-truth answer, and each backend's answer with its
verdict (and highlight wrong ones). `combined_results.json` already has every piece of that
joined and ready; the only remaining work is the presentation layer (e.g. a static HTML page that
iterates the `questions` array and renders each page image inline next to its answer table).
