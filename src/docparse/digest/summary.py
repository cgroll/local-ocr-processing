"""Title + summary per document, generated from the deterministic Markdown digest by the
`describe` model (reused here as a plain text model -- no new model, no new VRAM question).

Key finding from `experiments/digest-summary-test/`: with long documents (7000+ tokens), the
instruction MUST come after the document content, not before -- a 3B model otherwise loses the
instruction to a recency effect and just trails off echoing the end of the document. Verified
against three real documents (`ds-lm317`, `ds-tps62130`, `ntrs-19760010918`) with the instruction
placed last.

This does not touch the deterministic `<doc>.md` digest -- title/summary are stored separately
(`<doc>.summary.json`), so `document-digest`'s "no model call" guarantee for the `.md` itself
still holds.

**Known limitation, found when running this over all 73 documents (not just the 3 verified
above): ~18% (13/73) of real documents produced degenerate output** with the model's default
generation settings (`repetition_penalty=1.05`, near-zero temperature) -- empty output, a long
repeated-word loop ("Title Title Title..." x180), or the model echoing the prompt's own
delimiter text back verbatim instead of generating anything. A stronger `repetition_penalty`
(tried 1.3 + `no_repeat_ngram_size=4`) fixed one observed case but made another one *worse*
(coherent-looking multilingual gibberish, harder to detect than an obvious repeat loop) -- no
clean parameter fix found. The response here is detection, not a decoding-parameter workaround:
`_is_degenerate` flags the output and the caller marks `DocumentSummary.status = "degenerate"`
instead of silently treating garbage as a valid summary.
"""
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from ..models.lifecycle import ModelManager
from ..parse.format import RESULTS_DIR
from .document import DIGEST_SUBDIR

MAX_NEW_TOKENS = 220
MIN_OUTPUT_CHARS = 15
MAX_REPEATED_WORD_SHARE = 0.3  # a single word making up >30% of a >=20-word output is a loop
_PROMPT_ECHO_MARKERS = ("ENDDOCUMENTCONTENT", "DOCUMENTCONTENT(AUTOMATICALLYEXTRACTED")
# Catches character/pattern-level loops that the word-based check above misses because there's
# too little whitespace to split on (seen on gd1-001147: a LaTeX-table hallucination that is
# effectively one giant "word", "\begin{tabular}{|l|l|l|l|...}" repeated ~90 times).
_REPEATED_PATTERN_RE = re.compile(r"(.{1,6}?)\1{9,}")

PROMPT_TEMPLATE = """--- DOCUMENT CONTENT (automatically extracted: text, table contents, and \
descriptions of figures/charts) ---
{content}
--- END DOCUMENT CONTENT ---

Based only on the document above: write a short title line, then a 3-5 sentence summary \
paragraph of what this document is and what it covers. Do not list keywords. Format exactly as:
TITLE: <title>
SUMMARY: <paragraph>
"""

# Generic, not just <title>/<summary>: also seen "<paragraph>" (bs-f-831f, ntrs-20160001866,
# both with literally nothing else -- the model echoed the template's own placeholder verbatim
# instead of filling it in), "<abstract>" and "<ref lang=\"en\"><p>" (both with real content
# alongside, just wrapped in tag clutter). Matches any simple open/close tag, with or without
# attributes; deliberately requires a letter right after "<"/"</" so it cannot eat something
# like "<100ppm>" that happens to contain angle brackets without being a tag.
_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9_]*(?:\s+[^<>]*?)?\s*/?>")
# [ \t]*, not \s*, around the colon: \s* would happily cross the newline into the next labeled
# line when the title itself is empty (e.g. "TITLE: <title>\nSUMMARY: ..." with "<title>" already
# stripped to "") and capture "SUMMARY: ..." as the "title" instead of finding nothing.
_TITLE_RE = re.compile(r"TITLE[ \t]*:[ \t]*(.*)", re.IGNORECASE)
# (.*) , not (.+): must also match when nothing at all follows the label (e.g. "SUMMARY:" at the
# very end of the output), so that case reads as "label found, empty" rather than "no label
# found" -- which would otherwise fall back to reusing the whole (label-polluted) cleaned text.
_SUMMARY_RE = re.compile(r"SUMMARY\s*:[ \t]*(.*)", re.IGNORECASE | re.DOTALL)


@dataclass
class DocumentSummary:
    doc_id: str
    title: str
    summary: str
    status: str = "ok"  # "ok" | "degenerate"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DocumentSummary":
        return cls(**d)


def is_degenerate(raw_output: str) -> bool:
    """Catches the three failure patterns actually observed across the 73-document dataset:
    empty/near-empty output, a single word repeated into most of the output, and the model
    echoing the prompt's own delimiter text back instead of generating anything."""
    text = raw_output.strip()
    if len(text) < MIN_OUTPUT_CHARS:
        return True
    squashed = re.sub(r"\s+", "", text).upper()
    if any(marker in squashed for marker in _PROMPT_ECHO_MARKERS):
        return True
    if _REPEATED_PATTERN_RE.search(text):
        return True
    words = text.split()
    if len(words) >= 20:
        _, count = Counter(words).most_common(1)[0]
        if count / len(words) > MAX_REPEATED_WORD_SHARE:
            return True
    return False


def parse_title_summary(raw_output: str, fallback_title: str) -> tuple[str, str]:
    """Tolerant parsing: the model does not reliably emit the exact `TITLE:`/`SUMMARY:` format
    (seen: a missing title line, a bare `<title>` tag, a stray `<paragraph>`/`<abstract>` tag
    wrapping -- or replacing -- the real content). Falls back to `fallback_title` (the caller's
    doc_id) rather than guessing a title from the prose. Falls back to the whole cleaned output
    as the summary only when no `SUMMARY:` label was found at all -- if the label *was* found but
    captured nothing real (e.g. the model echoed just a placeholder tag that `_TAG_RE` then
    stripped to nothing), the summary is left empty rather than silently reusing the cleaned
    text, which would otherwise be "TITLE: ...\nSUMMARY:" junk. `generate_summary` treats an
    empty result here as degenerate."""
    cleaned = _TAG_RE.sub("", raw_output).strip()
    summary_match = _SUMMARY_RE.search(cleaned)
    summary = summary_match.group(1).strip() if summary_match else cleaned
    title_match = _TITLE_RE.search(cleaned)
    title_lines = title_match.group(1).splitlines() if title_match else []
    title = title_lines[0].strip() if title_lines else ""
    if title.rstrip(":").upper() in ("TITLE", "SUMMARY"):
        # Seen verbatim: the model wrote "TITLE: SUMMARY:" -- its own next label, not a title.
        title = ""
    return (title or fallback_title), summary


def generate_summary(manager: ModelManager, doc_id: str, digest_text: str) -> DocumentSummary:
    handle = manager.load("describe")
    prompt = PROMPT_TEMPLATE.format(content=digest_text)
    raw = handle.generate_text(prompt, max_new_tokens=MAX_NEW_TOKENS)
    if is_degenerate(raw):
        return DocumentSummary(doc_id, doc_id, "", status="degenerate")
    title, summary = parse_title_summary(raw, fallback_title=doc_id)
    if not summary.strip():
        return DocumentSummary(doc_id, doc_id, "", status="degenerate")
    return DocumentSummary(doc_id, title, summary, status="ok")


def summary_path(doc_id: str, root: Path = RESULTS_DIR) -> Path:
    return root / DIGEST_SUBDIR / f"{doc_id}.summary.json"


def write_summary(summary: DocumentSummary, root: Path = RESULTS_DIR) -> Path:
    path = summary_path(summary.doc_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def read_summary(path: Path) -> DocumentSummary:
    return DocumentSummary.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
