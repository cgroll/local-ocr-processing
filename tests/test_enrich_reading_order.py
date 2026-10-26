"""Column-aware reading order: PP-OCRv6 (and occasionally pymupdf) orders blocks by raw
y-position across the whole page, which interleaves left/right column text into word salad on
multi-column pages -- a real case found on bs-f-831f-pdp-8-interface-manual-may65 p2. See
`enrich/blocks.py:reading_order`."""
from docparse.enrich.blocks import reading_order
from docparse.parse.format import Block

PAGE_W, PAGE_H = 1275.0, 1650.0


def _block(order: int, x0: float, y0: float, text: str) -> Block:
    return Block(type="line", label="text_line", bbox=[x0, y0, x0 + 500, y0 + 30], engine="ocr", order=order, text=text)


def _two_columns():
    """Mirrors the real bs-f-831f case: OCR's own order alternates left/right line by line."""
    left = [_block(2 * i, 85.0, 150.0 + i * 300, f"left column line number {i} with real words") for i in range(4)]
    right = [_block(2 * i + 1, 677.0, 150.0 + i * 300, f"right column line number {i} with real words") for i in range(4)]
    interleaved = []
    for l, r in zip(left, right):
        interleaved.extend([l, r])
    return interleaved, left, right


def test_interleaved_two_column_blocks_are_regrouped_by_column():
    interleaved, left, right = _two_columns()
    ordered = reading_order(interleaved, PAGE_W, PAGE_H)
    assert ordered == left + right  # left column fully, then right column fully, each top-to-bottom


def test_single_column_page_is_unaffected():
    blocks = [_block(i, 85.0, 150.0 + i * 300, f"line number {i} with enough real words here") for i in range(4)]
    assert reading_order(blocks, PAGE_W, PAGE_H) == blocks


def test_scattered_schematic_labels_are_not_treated_as_columns():
    # Short labels scattered across many different x-positions (a schematic, not running prose)
    # must fall back to the original order, not get scrambled by a false-positive column split.
    xs = [85.0, 250.0, 420.0, 600.0, 780.0, 950.0]
    blocks = [_block(i, x, 150.0 + (i % 3) * 40, "VOS") for i, x in enumerate(xs)]
    assert reading_order(blocks, PAGE_W, PAGE_H) == sorted(blocks, key=lambda b: b.order)


def test_columns_that_do_not_span_most_of_the_page_height_are_not_reordered():
    # Two x-clusters, but each only covers a small vertical sliver -- e.g. a short two-column
    # caption, not a genuine multi-column page -- should not trigger reordering.
    left = [_block(2 * i, 85.0, 150.0 + i * 20, f"left line {i} with words here") for i in range(4)]
    right = [_block(2 * i + 1, 677.0, 150.0 + i * 20, f"right line {i} with words here") for i in range(4)]
    interleaved = [b for pair in zip(left, right) for b in pair]
    assert reading_order(interleaved, PAGE_W, PAGE_H) == sorted(interleaved, key=lambda b: b.order)


def test_too_few_blocks_per_column_is_not_reordered():
    left = [_block(2 * i, 85.0, 150.0 + i * 300, f"left line {i} with real words here") for i in range(2)]
    right = [_block(2 * i + 1, 677.0, 150.0 + i * 300, f"right line {i} with real words here") for i in range(2)]
    interleaved = [b for pair in zip(left, right) for b in pair]
    assert reading_order(interleaved, PAGE_W, PAGE_H) == sorted(interleaved, key=lambda b: b.order)


def test_zero_page_dimensions_fall_back_safely():
    interleaved, _, _ = _two_columns()
    assert reading_order(interleaved, 0, 0) == sorted(interleaved, key=lambda b: b.order)
