"""PaddleOCR-VL-1.6 parsing blocks -> blocks with markdown / html."""
from ..format import Block
from ..labels import block_type


def to_blocks(raw: list[dict]) -> list[Block]:
    """`raw` is one dict per parsing block: label, bbox, content, optional polygon_points; list order is reading order."""
    blocks = []
    for i, b in enumerate(raw):
        content = (b.get("content") or "").strip()
        typ = block_type(b["label"])
        is_html = "<table" in content
        blocks.append(Block(
            type=typ, label=b["label"], bbox=[float(v) for v in b["bbox"]], engine="vl", order=i,
            polygon=[[float(x), float(y)] for x, y in b["polygon_points"]] if b.get("polygon_points") is not None else None,
            text=None if is_html or not content else content,
            markdown=None if is_html or not content else content,
            html=content if is_html else None,
        ))
    return blocks
