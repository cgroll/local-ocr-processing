# Agentic retrieval eval

**Not production code; not part of `src/docparse`.** Informal comparison spike, same status as
`experiments/vlm-qa-test/`, `experiments/digest-summary-test/`, `experiments/multimodal-repr-test/`
-- see `openspec/changes/agentic-retrieval-eval/` for the proposal/design behind this.

## Question

Does the document-level summary quality (local `describe`-model vs. Gemini-4-Argon cloud
summary, see `cloud-document-summary`) make a measurable difference once an agent has to find
the right content itself via the search index, instead of being handed the correct page directly
(as in the original `experiments/vlm-qa-test/`)?

## Result (full run, 2026-10-26)

**No.** 19/20 questions correct in both variants (same single failure in both -- a genuinely
ambiguous follow-up question, not a summary-quality issue), and no consistent efficiency
difference (tool calls, documents visited, cost) either. Full numbers, methodology notes and the
pilot that preceded the full run: `openspec/changes/agentic-retrieval-eval/pilot-notes.md` and
`full-run-results.md`.

Headline cost: **$5.08** total for 40 agent runs + 40 Gemini-judge verdicts.

## How it works

1. `build_sandbox.py` builds two throwaway corpus copies (`sandbox_local/`, `sandbox_cloud/`)
   from `data/results/{enrich,digest,search}` + `data/pages` -- identical except for which
   document-summary file and which document-level embedding kind is present. Ground truth
   (`experiments/vlm-qa-test/questions.py`) is never a source.
2. `Dockerfile` + `sandbox_tools/` build a CPU-only image (no PaddlePaddle/CUDA) that can run
   EmbeddingGemma 2 (via `sentence-transformers`, from the local HF cache) and the Claude Agent
   SDK.
3. `sandbox_tools/run_agent.py` runs *inside* the container (the container boundary is the
   isolation, not just `cwd`) and drives one Claude session per question: only `Bash`+`Read`
   tools, only the question text (no document/page hint), with a hard requirement to view the
   actual page PNG before answering.
4. `analyze_run.py` turns the raw transcript into a compact efficiency summary (tool calls,
   documents visited, tokens/cost/duration).
5. `judge.py` scores the final answer against `vlm-qa-test`'s ground truth via Gemini 4 Argon
   (not Claude, so the grader isn't the same model family as the agent being graded).
6. `run_pilot.py` orchestrates runs over a question-id list x both variants (used for both the
   pilot and the full run -- same script, different `--question-ids`).

## Reproducing

```bash
# 1. One-time: build the sandbox image
docker build -t agentic-retrieval-eval-sandbox .

# 2. Build a redacted Claude credentials snapshot (NOT the real ~/.claude/.credentials.json --
#    that file also holds other services' OAuth tokens, e.g. MCP servers). Short-lived: the
#    OAuth token can get revoked after a few hours if the real host session rotates its own
#    token in the meantime (hit this during the full run -- see full-run-results.md).
python3 -c "
import json
d = json.load(open('/home/<user>/.claude/.credentials.json'))
json.dump({'claudeAiOauth': d['claudeAiOauth']}, open('/tmp/claude_config_dir/.credentials.json', 'w'))
"

# 3. Build the two sandboxes (needs the project venv, for docparse.search.format)
uv run python experiments/agentic-retrieval-eval/build_sandbox.py --out-dir /tmp/sandboxes

# 4. Run some questions x both variants
uv run python experiments/agentic-retrieval-eval/run_pilot.py \
  --question-ids 1a 1b --sandboxes-dir /tmp/sandboxes --out-dir /tmp/agent_output

# 5. Judge the answers (see judge.py's own __main__ for a single-answer example, or the
#    inline loop used for the full run in full-run-results.md's "Reproducing" notes)
```

## Known limitations

- Doc-visit counting in `analyze_run.py` is a path-regex heuristic over tool-call arguments, not
  a precise trace.
- The mandatory image-verification step is a prompt instruction, not technically enforced --
  `image_verified` in the summary just reflects whether a `Read` on a `/sandbox/pages/*.png` was
  observed in the transcript.
- Ground-truth secrecy is "weak" by design (the sandbox simply never contains it, not a verified
  technical guarantee against a maximally adversarial agent) -- accepted trade-off for this scale
  of spike, see `design.md`.
- n=1 per question/variant cell -- a single agent run has real run-to-run variance (different
  search paths, different prompt-cache hit/miss state affecting cost). The full run's effect
  sizes are small enough that they could plausibly be noise; this was not repeated to confirm.
