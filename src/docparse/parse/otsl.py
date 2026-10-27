"""OTSL (PaddleOCR's Optical Table Sequence Language) -> HTML table.

PaddleOCR-VL emits tables as a token stream (`<fcel>cell<ecel><nl>...`): <fcel> filled cell,
<ecel> empty cell, <lcel> horizontal merge (colspan), <ucel> vertical merge (rowspan), <xcel> both,
<nl> new row. The Paddle pipeline (CUDA path) returns tables already as HTML, so this conversion is
only needed on the MLX path, where PaddleOCR-VL's raw table output is OTSL. Ported from
~/repos/EEP/eep/otsl.py; uses paddlex's reference decoder when available, with a minimal fallback.
"""
from __future__ import annotations

import html
import re

TAGS = ("<fcel>", "<ecel>", "<lcel>", "<ucel>", "<xcel>", "<nl>")


def looks_like_otsl(text: str) -> bool:
    return sum(text.count(t) for t in TAGS) >= 2


def otsl_to_html(otsl: str) -> str:
    if not otsl or not any(t in otsl for t in TAGS):
        return otsl
    try:
        from paddlex.inference.pipelines.paddleocr_vl.uilts import convert_otsl_to_html

        return convert_otsl_to_html(otsl)
    except Exception:
        return _fallback_html(otsl)


# --- helpers ---------------------------------------------------------------

def _fallback_text_rows(otsl: str) -> str:
    out = re.sub(r"<(fcel|ecel|xcel|lcel|ucel)>", "|", otsl)
    return out.replace("<nl>", "\n")


def _fallback_html(otsl: str) -> str:
    lines = _fallback_text_rows(otsl).split("\n")
    parts = ["<table>"]
    for i, line in enumerate(lines):
        if not line.strip("|"):
            continue
        cells = line.split("|")[1:-1] if line.startswith("|") else line.split("|")
        tag = "th" if i == 0 else "td"
        parts.append("<tr>" + "".join(f"<{tag}>{html.escape(c.strip())}</{tag}>" for c in cells) + "</tr>")
    parts.append("</table>")
    return "\n".join(parts)
