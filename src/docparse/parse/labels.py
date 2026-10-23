"""Map engine labels (PP-DocLayoutV3 label set, also used by PaddleOCR-VL) to block types."""
from .format import BLOCK_TYPES

LAYOUT_LABELS = {
    "abstract": "text",
    "algorithm": "text",
    "aside_text": "text",
    "chart": "chart",
    "content": "text",  # table of contents
    "display_formula": "formula",
    "doc_title": "title",
    "figure_title": "caption",
    "footer": "footer",
    "footer_image": "figure",
    "footnote": "text",
    "formula_number": "formula",
    "header": "header",
    "header_image": "figure",
    "image": "figure",
    "inline_formula": "formula",
    "number": "footer",  # page number
    "paragraph_title": "title",
    "reference": "text",
    "reference_content": "text",
    "seal": "figure",
    "table": "table",
    "text": "text",
    "vertical_text": "text",
    "vision_footnote": "text",
}

assert set(LAYOUT_LABELS.values()) <= set(BLOCK_TYPES)


def block_type(label: str) -> str:
    return LAYOUT_LABELS.get(label, "other")
