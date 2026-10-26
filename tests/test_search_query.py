import numpy as np

from docparse.search.format import EmbeddingIndex, EmbeddingItem
from docparse.search.fulltext import Document, FullTextIndex
from docparse.search.query import search


class FakeEmbeddingModel:
    """encode(query, prompt_name="SearchQuery") returns a vector that is closest (by cosine) to
    whichever stored vector shares its first component -- lets tests control which row "wins"
    via a 2-char "q1"/"v2"-style tag; any other text falls back to an arbitrary fixed vector."""
    def encode(self, text, prompt_name=None):
        tag = float(text[1]) if len(text) == 2 and text[0] in "qv" and text[1].isdigit() else 0.0
        return np.array([tag, 1.0, 0.0], dtype=np.float32)


class FakeManager:
    def load(self, key):
        return FakeEmbeddingModel()


def make_embedding_index():
    items = [
        EmbeddingItem("d/0001/PAGE_TEXT", "d", 1, "page_text", 0),
        EmbeddingItem("d/0002/PAGE_TEXT", "d", 2, "page_text", 1),
    ]
    vectors = np.array([[1.0, 1.0, 0.0], [2.0, 1.0, 0.0]], dtype=np.float32)
    return EmbeddingIndex(items, vectors)


def make_fulltext_index():
    return FullTextIndex([Document("d/0001/NARRATIVE", "d", 1, "narrative", "PSRR value table")])


def test_search_combines_fulltext_and_vector_hits_with_source_tags():
    hits = search("PSRR", make_embedding_index(), make_fulltext_index(), FakeManager())
    sources = {h.source for h in hits}
    assert sources == {"fulltext", "vector"}
    assert any(h.source == "fulltext" and h.page == 1 for h in hits)
    assert any(h.source == "vector" for h in hits)


def test_search_vector_hit_ranks_the_closer_item_first():
    hits = search("q1", make_embedding_index(), FullTextIndex([]), FakeManager(), top_k=2)
    vector_hits = [h for h in hits if h.source == "vector"]
    assert vector_hits[0].key == "d/0001/PAGE_TEXT"  # tag 1.0 matches row 0 exactly


def test_search_without_manager_returns_fulltext_only():
    hits = search("PSRR", make_embedding_index(), make_fulltext_index(), manager=None)
    assert hits and all(h.source == "fulltext" for h in hits)


def test_search_with_empty_index_and_no_hits_returns_empty_list():
    hits = search("nothing matches this", EmbeddingIndex(), FullTextIndex([]), FakeManager())
    assert hits == []
