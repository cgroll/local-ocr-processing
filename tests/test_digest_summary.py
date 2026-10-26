from docparse.digest.summary import DocumentSummary, generate_summary, is_degenerate, parse_title_summary, read_summary, write_summary


class FakeHandle:
    def __init__(self, raw_output: str):
        self.raw_output = raw_output
        self.prompts = []

    def generate_text(self, prompt, max_new_tokens=None):
        self.prompts.append(prompt)
        return self.raw_output


class FakeManager:
    def __init__(self, raw_output: str):
        self.handle = FakeHandle(raw_output)

    def load(self, key):
        assert key == "describe"
        return self.handle


# --- parse_title_summary: tolerant parsing -----------------------------------

def test_parses_exact_format():
    title, summary = parse_title_summary("TITLE: LM317\nSUMMARY: An adjustable regulator.", "fallback")
    assert title == "LM317" and summary == "An adjustable regulator."


def test_missing_title_falls_back():
    title, summary = parse_title_summary("SUMMARY: Just a summary, no title line.", "ds-lm317")
    assert title == "ds-lm317" and summary == "Just a summary, no title line."


def test_bare_placeholder_tag_parses_to_empty_summary():
    # The real bs-f-831f / ntrs-20160001866 failure: the model echoed the prompt's own
    # unfilled placeholder instead of generating anything.
    title, summary = parse_title_summary("TITLE: <title>\nSUMMARY: <paragraph>", "doc-1")
    assert title == "doc-1" and summary == ""


def test_placeholder_tag_with_real_content_is_cleaned_not_dropped():
    # The real ds-ap2112 / gd1-001680 case: real content, just wrapped in tag clutter.
    title, summary = parse_title_summary(
        'TITLE: AP2112\nSUMMARY: <ref lang="en"><p>Ap2112 is a CMOS low dropout regulator.</p></ref>',
        "doc-1",
    )
    assert title == "AP2112" and summary == "Ap2112 is a CMOS low dropout regulator."


def test_title_that_is_just_the_summary_label_falls_back():
    # Real bs-kc8-a-schem case: raw model output was literally "TITLE: SUMMARY:\n\n<paragraph>\n
    # This document is...` -- the model wrote its own next label as the title.
    title, summary = parse_title_summary(
        "TITLE: SUMMARY:\n\n<paragraph>\nThis document is a technical specification sheet.",
        "doc-1",
    )
    assert title == "doc-1" and summary == "This document is a technical specification sheet."


def test_angle_bracket_value_is_not_mistaken_for_a_tag():
    # A tag must start with a letter right after "<"/"</" -- a value like "<100ppm>" must survive.
    title, summary = parse_title_summary("SUMMARY: Drift is <100ppm> over the rated range.", "doc-1")
    assert summary == "Drift is <100ppm> over the rated range."


def test_broken_tag_is_stripped_and_summary_still_found():
    title, summary = parse_title_summary("<title>\nSummary: content here", "ds-tps62130")
    assert title == "ds-tps62130" and summary == "content here"


def test_no_labels_at_all_uses_whole_output_as_summary():
    title, summary = parse_title_summary("Just plain prose with no labels.", "ds-x")
    assert title == "ds-x" and summary == "Just plain prose with no labels."


def test_multiline_summary_is_captured_fully():
    title, summary = parse_title_summary("TITLE: X\nSUMMARY: line one.\nline two.", "fallback")
    assert title == "X" and summary == "line one.\nline two."


# --- is_degenerate: the three failure patterns actually seen across the 73-doc dataset --------

def test_empty_output_is_degenerate():
    assert is_degenerate("") is True
    assert is_degenerate("   ") is True


def test_repeated_word_loop_is_degenerate():
    assert is_degenerate(" ".join(["Title"] * 180)) is True


def test_prompt_echo_is_degenerate():
    assert is_degenerate("--- END DOCUMENTCONTENT --") is True


def test_character_level_repetition_is_degenerate():
    # gd1-001147's real failure: a LaTeX-table hallucination with too little whitespace for the
    # word-repetition check to catch ("\begin{tabular}{|l|l|l|...}" is one giant "word").
    text = "Document Title\n\\begin{table}}\n\\begin{tabular}{" + "|l" * 90 + "}"
    assert is_degenerate(text) is True


def test_normal_summary_is_not_degenerate():
    text = "TITLE: LM317\nSUMMARY: An adjustable three-pin positive voltage regulator with a wide output range."
    assert is_degenerate(text) is False


def test_short_but_real_title_is_not_falsely_flagged():
    # below the word-repetition check's 20-word threshold, and above the min-length floor
    assert is_degenerate("TITLE: NE555 Timer\nSUMMARY: A precision timing circuit.") is False


# --- generate_summary marks degenerate output instead of treating it as valid -----------------

def test_generate_summary_marks_degenerate_output():
    manager = FakeManager(" ".join(["Title"] * 180))
    result = generate_summary(manager, "doc-1", "content")
    assert result.status == "degenerate" and result.title == "doc-1" and result.summary == ""


def test_generate_summary_marks_ok_for_normal_output():
    manager = FakeManager("TITLE: X\nSUMMARY: Y")
    result = generate_summary(manager, "doc-1", "content")
    assert result.status == "ok"


def test_generate_summary_marks_degenerate_for_bare_placeholder_tag():
    # Long enough and structured enough to pass is_degenerate(), but parses down to nothing --
    # must still end up "degenerate", not a status of "ok" with an empty/junk summary.
    manager = FakeManager("TITLE: <title>\nSUMMARY: <paragraph>")
    result = generate_summary(manager, "doc-1", "content")
    assert result.status == "degenerate" and result.summary == "" and result.title == "doc-1"


# --- generate_summary ---------------------------------------------------------

def test_generate_summary_uses_describe_and_parses_result():
    manager = FakeManager("TITLE: My Doc\nSUMMARY: A short summary.")
    result = generate_summary(manager, "doc-1", "full digest text")
    assert result == DocumentSummary("doc-1", "My Doc", "A short summary.")
    assert "full digest text" in manager.handle.prompts[0]


def test_generate_summary_puts_content_before_instruction():
    # The recency-effect finding from experiments/digest-summary-test/: the instruction must
    # come after the document content in the prompt, not before.
    manager = FakeManager("TITLE: X\nSUMMARY: Y")
    generate_summary(manager, "doc-1", "THE DOCUMENT BODY")
    prompt = manager.handle.prompts[0]
    assert prompt.index("THE DOCUMENT BODY") < prompt.index("write a short title line")


# --- read/write round trip -----------------------------------------------------

def test_summary_round_trip(tmp_path):
    summary = DocumentSummary("doc-1", "Title", "Summary text")
    path = write_summary(summary, tmp_path)
    assert read_summary(path) == summary
