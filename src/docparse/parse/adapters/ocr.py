"""PP-OCRv6 text lines -> `line` blocks."""
from ..format import Block


def to_blocks(raw: dict) -> list[Block]:
    """`raw` holds rec_texts, rec_scores, rec_polys and rec_boxes of one page."""
    blocks = []
    for i, (text, score, poly, box) in enumerate(zip(raw["rec_texts"], raw["rec_scores"], raw["rec_polys"], raw["rec_boxes"])):
        blocks.append(Block(
            type="line", label="text_line", bbox=[float(v) for v in box], engine="ocr", order=i,
            confidence=float(score), polygon=[[float(x), float(y)] for x, y in poly], text=text,
        ))
    return blocks
