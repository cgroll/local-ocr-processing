"""Manual verdicts for the informal VLM QA test (filled in by reading each page + each model's answer).

verdict values: "correct", "partial", "wrong"
Not production code; see experiments/vlm-qa-test/README for context.
"""

# Filled in after all four backends produced raw_*.json and each answer was compared against
# the page image by hand (2026-10-25). Keyed by question id -> backend -> {verdict, note}.
# Backend keys match the raw_<backend>.json filenames: qwen3b, qwen7b, gemma, paddle_vl.
JUDGMENTS: dict[str, dict[str, dict]] = {
    "1a": {  # PSRR(120Hz) LM317-N @1.5A = 80 dB (ground_truth correct, verified against table)
        "qwen3b": {"verdict": "correct", "note": "80 dB"},
        "qwen7b": {"verdict": "correct", "note": "80 dB"},
        "gemma": {"verdict": "correct", "note": "80 dB"},
        "paddle_vl": {"verdict": "wrong", "note": "OCR dump truncated at 100 tokens before reaching PSRR row; no answer given"},
        "gemini_argon": {"verdict": "correct", "note": "80 dB"},
    },
    "1b": {  # LM317HV recommended op temp @1.5A = 0 to 125 C (ground_truth correct; table has a
             # separate -40 to 125 column for LM317A at the same row -- easy to confuse)
        "qwen3b": {"verdict": "correct", "note": "0 to 125 C"},
        "qwen7b": {"verdict": "wrong", "note": "said -40 to 125 C -- that's the LM317A column, not LM317HV"},
        "gemma": {"verdict": "wrong", "note": "same column mix-up as qwen7b, -40 to 125 C"},
        "paddle_vl": {"verdict": "wrong", "note": "dump cut off before the 'Recommended operating temperature' row"},
        "gemini_argon": {"verdict": "correct", "note": "0 to 125 C -- correct column, no mix-up"},
    },
    "2a": {  # TRIG pin on NA555 D/P package = pin 2 (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "pin 2"},
        "qwen7b": {"verdict": "correct", "note": "pin 2"},
        "gemma": {"verdict": "wrong", "note": "said pin 5 -- that's CONT, not TRIG"},
        "paddle_vl": {"verdict": "wrong", "note": "dump of package/title text, never reaches the pin table"},
        "gemini_argon": {"verdict": "correct", "note": "pin 2"},
    },
    "2b": {  # VCC input range = 4.5V to 16V, SE555 max 18V (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "4.5V-16V, SE555 max 18V -- matches table exactly"},
        "qwen7b": {"verdict": "partial", "note": "4.5V-16V correct but drops the SE555-max-18V caveat"},
        "gemma": {"verdict": "wrong", "note": "said 4.5V to 18V, conflating the general range with the SE555-only max"},
        "paddle_vl": {"verdict": "wrong", "note": "dump of package list, never reaches the VCC row"},
        "gemini_argon": {"verdict": "correct", "note": "4.5V-16V, SE555 max 18V -- matches table exactly"},
    },
    "3a": {  # Output cap at VOS/output in typical application schematic = 22 uF (ground_truth correct)
        "qwen3b": {"verdict": "wrong", "note": "said 100 uF -- no such value appears anywhere on the page"},
        "qwen7b": {"verdict": "correct", "note": "22 uF"},
        "gemma": {"verdict": "wrong", "note": "said 0.1 uF -- that's the AVIN decoupling cap, not the output cap"},
        "paddle_vl": {"verdict": "wrong", "note": "dump stuck on ordering/features section, never reaches the schematic"},
        "gemini_argon": {"verdict": "correct", "note": "22 uF"},
    },
    "3b": {  # Efficiency vs output current: highest curve = VIN=5V (ground_truth correct;
             # verified visually -- black 5V curve sits on top across most of the x-axis)
        "qwen3b": {"verdict": "wrong", "note": "said VIN=17V -- that's actually the lowest curve"},
        "qwen7b": {"verdict": "wrong", "note": "said VIN=12V -- that's the middle curve"},
        "gemma": {"verdict": "wrong", "note": "said VIN=12V, same mistake as qwen7b"},
        "paddle_vl": {"verdict": "wrong", "note": "dump of features list, never reaches the graph"},
        "gemini_argon": {"verdict": "correct", "note": "VIN=5V -- correctly identifies the top curve"},
    },
    "4a": {  # Continuous drain current ID @ TC=25C = 28 A (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "28 A"},
        "qwen7b": {"verdict": "correct", "note": "28 A"},
        "gemma": {"verdict": "wrong", "note": "said 20A -- that's the TC=100C row, not TC=25C"},
        "paddle_vl": {"verdict": "wrong", "note": "dump of features list, never reaches the ratings table"},
        "gemini_argon": {"verdict": "correct", "note": "28 A"},
    },
    "4b": {  # Package = TO-220AB (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "TO-220AB"},
        "qwen7b": {"verdict": "correct", "note": "TO-220AB"},
        "gemma": {"verdict": "correct", "note": "TO-220AB"},
        "paddle_vl": {"verdict": "wrong", "note": "dump starts mid-header, never includes the TO-220AB label"},
        "gemini_argon": {"verdict": "correct", "note": "TO-220AB"},
    },
    "5a": {  # Overall height, PDP-8 in CAB-8B = 69 1/8 in (ground_truth correct, verified on drawing)
        "qwen3b": {"verdict": "wrong", "note": "said 69 3/8 in -- misread the fraction"},
        "qwen7b": {"verdict": "wrong", "note": "said 69 5/8 in -- misread the fraction"},
        "gemma": {"verdict": "wrong", "note": "said 69 5/8 in -- same misread as qwen7b"},
        "paddle_vl": {"verdict": "wrong", "note": "garbled OCR of the dimension labels as 'Component 22%/27%/16%/26%', no height given"},
        "gemini_argon": {"verdict": "correct", "note": "69 1/8 in -- correct fraction, the one every other model misread"},
    },
    "5b": {  # Power Supply height = 8 in (ground_truth correct, plain '8' on the left edge of
             # the Power Supply isometric drawing)
        "qwen3b": {"verdict": "wrong", "note": "said 17 5/8 in -- that's a width label on a different component"},
        "qwen7b": {"verdict": "wrong", "note": "said 9 1/2 in -- close to the 9 11/16 label but that's a partial segment, not the full height"},
        "gemma": {"verdict": "wrong", "note": "said 5 5/8 in -- doesn't match any label in the Power Supply drawing"},
        "paddle_vl": {"verdict": "wrong", "note": "dump of the unrelated PDP-8 cabinet dimensions (wrong drawing on the page)"},
        "gemini_argon": {"verdict": "correct", "note": "8 in as the primary chassis height, also correctly notes 9 11/16 as a separate front-panel dimension"},
    },
    "6a": {  # F2 Logic: pin 3 -> +12 VDC bus (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "pin 3"},
        "qwen7b": {"verdict": "correct", "note": "pin 3"},
        "gemma": {"verdict": "correct", "note": "pin 3"},
        "paddle_vl": {"verdict": "correct", "note": "table dump includes the correct row verbatim"},
        "gemini_argon": {"verdict": "correct", "note": "pin 3"},
    },
    "6b": {  # F2 Logic: pin V -> Ground bus (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "pin V"},
        "qwen7b": {"verdict": "correct", "note": "pin V"},
        "gemma": {"verdict": "correct", "note": "pin V"},
        "paddle_vl": {"verdict": "wrong", "note": "answered 'F2 Logic4' -- nonsense, doesn't address the question"},
        "gemini_argon": {"verdict": "correct", "note": "pin V"},
    },
    "7a": {  # Fig II-1 drawing number = D-TD-RK01-X-12 (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "D-TD-RK01-X-12"},
        "qwen7b": {"verdict": "correct", "note": "D-TD-RK01-X-12"},
        "gemma": {"verdict": "partial", "note": "dropped a dash: D-TD-RK01-X12 instead of D-TD-RK01-X-12"},
        "paddle_vl": {"verdict": "correct", "note": "table dump includes the correct drawing number verbatim"},
        "gemini_argon": {"verdict": "correct", "note": "D-TD-RK01-X-12 -- exact match, correct dash placement"},
    },
    "7b": {  # Fig II-39 title = "Type 716 Power Supply Circuit Schematic Diagram" (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "exact match"},
        "qwen7b": {"verdict": "correct", "note": "exact match"},
        "gemma": {"verdict": "wrong", "note": "hallucinated 'AC Power Gating to 64K Block Schematic Diagram' -- not in the contents table at all"},
        "paddle_vl": {"verdict": "wrong", "note": "dump cut off before the Power Supply section of the contents table"},
        "gemini_argon": {"verdict": "correct", "note": "exact match, no hallucination"},
    },
    "8a": {  # JAN column max daily discharge = 5730 cfs (ground_truth correct, matches the MAX row)
        "qwen3b": {"verdict": "wrong", "note": "said 147 -- that's an OCT value, not the JAN max"},
        "qwen7b": {"verdict": "wrong", "note": "said 1810 -- a JAN daily value (day 29), not the max"},
        "gemma": {"verdict": "wrong", "note": "said 1760 -- that's a FEB value, not JAN"},
        "paddle_vl": {"verdict": "wrong", "note": "dump of location text, never reaches the discharge table"},
        "gemini_argon": {"verdict": "correct", "note": "5730 cfs -- correctly reads the MAX row, not a daily value"},
    },
    "8b": {  # Drainage area = 290 mi^2 (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "290 mi^2"},
        "qwen7b": {"verdict": "correct", "note": "290 square miles"},
        "gemma": {"verdict": "correct", "note": "290 mi^2"},
        "paddle_vl": {"verdict": "wrong", "note": "dump truncated right before the 'DRAINAGE AREA--290 mi^2' line"},
        "gemini_argon": {"verdict": "correct", "note": "290 mi^2"},
    },
    "9a": {  # Cover title = "California Grape Acreage 2006 Crop" (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "exact match"},
        "qwen7b": {"verdict": "correct", "note": "exact match"},
        "gemma": {"verdict": "correct", "note": "exact match"},
        "paddle_vl": {"verdict": "correct", "note": "exact match"},
        "gemini_argon": {"verdict": "correct", "note": "exact match"},
    },
    "9b": {  # Open/descriptive: vineyard landscape, grapevines foreground, hills/vine rows behind
        "qwen3b": {"verdict": "correct", "note": "vineyard, grapevine rows foreground, hills behind -- matches"},
        "qwen7b": {"verdict": "correct", "note": "same, with more detail, matches"},
        "gemma": {"verdict": "partial", "note": "content matches but vaguer, plus an odd unprompted offer to analyze the report data tacked on"},
        "paddle_vl": {"verdict": "wrong", "note": "doesn't describe the photo at all, just re-OCRs the title/publisher text"},
        "gemini_argon": {"verdict": "correct", "note": "detailed, accurate description (foreground vines, midground tree/hills, background ridges)"},
    },
    "10a": {  # Author = David M. Henderson, TRW Houston (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "exact match"},
        "qwen7b": {"verdict": "correct", "note": "exact match"},
        "gemma": {"verdict": "correct", "note": "exact match"},
        "paddle_vl": {"verdict": "correct", "note": "dump includes the author/affiliation lines verbatim"},
        "gemini_argon": {"verdict": "correct", "note": "exact match"},
    },
    "10b": {  # Abstract: three (3) regions of mathematical description (ground_truth correct)
        "qwen3b": {"verdict": "correct", "note": "says three, no further embellishment"},
        "qwen7b": {"verdict": "correct", "note": "says three; itemized sub-descriptions are paraphrased/partly inaccurate but the asked-for count is right"},
        "gemma": {"verdict": "correct", "note": "says three; itemized sub-descriptions are garbled/hallucinated but the asked-for count is right"},
        "paddle_vl": {"verdict": "correct", "note": "dump includes 'three different regions of mathematical description' verbatim"},
        "gemini_argon": {"verdict": "correct", "note": "says three, no fabricated elaboration"},
    },
}
