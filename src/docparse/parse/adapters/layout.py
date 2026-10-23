"""PP-DocLayoutV3 boxes -> blocks (no text)."""
from ..format import Block
from ..labels import block_type


def to_blocks(boxes: list[dict]) -> list[Block]:
    return [
        Block(
            type=block_type(b["label"]), label=b["label"], bbox=[float(v) for v in b["coordinate"]],
            engine="layout", order=b.get("order"), confidence=float(b["score"]),
            polygon=[[float(x), float(y)] for x, y in b["polygon_points"]] if b.get("polygon_points") is not None else None,
        )
        for b in boxes
    ]
