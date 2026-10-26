"""Short, topic-level VLM descriptions for figure/chart/table crops (see the `page-enrichment`
spec: descriptions name the kind/topic of the content, never specific values). Prompts carried
over from experiments/multimodal-repr-test/build_rich_page.py, where they were validated
against two example pages (a table-dominant datasheet page and a schematic+chart page) -- see
that experiment's README for the qualitative check."""
from PIL import Image

from ..models.lifecycle import ModelManager

PROMPTS = {
    "table": (
        "Look at this image of a table from a technical document. In exactly one sentence, "
        "describe what the table is about in general terms -- its topic and structure (e.g. "
        "'a comparison of electrical parameters across several product variants, grouped by "
        "output current'). Do NOT state any specific numeric values or name individual rows/"
        "columns verbatim."
    ),
    "figure": (
        "Look at this image from a technical document page. In exactly one sentence, describe "
        "what kind of figure this is (e.g. 'a schematic circuit diagram with an IC and passive "
        "components', 'a photograph of a component package', 'a block diagram of a system'). "
        "Do NOT state specific numeric values, part numbers, or exact readings."
    ),
    "chart": (
        "Look at this image from a technical document page. In exactly one sentence, describe "
        "what kind of chart/graph this is and what it plots in general terms (e.g. 'a line graph "
        "of efficiency versus output current for several input voltages'). Do NOT state specific "
        "numeric values or which curve is highest/lowest."
    ),
}


def describe(manager: ModelManager, image: Image.Image, block_type: str) -> str:
    """Loads `describe` (cached after the first call -- the caller decides when to unload)."""
    handle = manager.load("describe")
    return handle.describe(image, PROMPTS[block_type])
