import pytest

from docparse.enrich.format import PageEnrichment, VisualBlock, write_result as write_enrichment
from docparse.search.fulltext import Document, FullTextIndex, enriched_documents, fts5_available


def test_fts5_is_available_in_this_environment():
    # Documents this test environment's actual capability (task 6.1); the fallback path is
    # exercised directly below regardless, so both code paths are covered either way.
    assert fts5_available() is True


def _write(root, doc_id, page, narrative="", visual_blocks=None):
    write_enrichment(PageEnrichment(doc_id, page, "pymupdf", narrative_text=narrative,
                                     visual_blocks=visual_blocks or []), root)


def test_enriched_documents_covers_narrative_description_and_content(tmp_path):
    _write(tmp_path, "d", 1, narrative="PSRR is high", visual_blocks=[
        VisualBlock(type="table", label="table", bbox=[0, 0, 1, 1], position=0, crop_path="x.png",
                    description="a parameter table", content_text="<table><td>PSRR</td></table>"),
    ])
    docs = enriched_documents(tmp_path)
    kinds = {d.kind for d in docs}
    assert kinds == {"narrative", "visual_desc", "visual_content"}
    assert all(d.doc_id == "d" and d.page == 1 for d in docs)


@pytest.mark.parametrize("use_fts5", [True, False])
def test_search_finds_a_literal_term_in_table_content(tmp_path, use_fts5):
    _write(tmp_path, "d", 1, narrative="unrelated text", visual_blocks=[
        VisualBlock(type="table", label="table", bbox=[0, 0, 1, 1], position=0, crop_path="x.png",
                    content_text="PSRR (120Hz) value is 80 dB"),
    ])
    _write(tmp_path, "d", 2, narrative="a completely different page about capacitors")
    index = FullTextIndex(enriched_documents(tmp_path), use_fts5=use_fts5)
    hits = index.search("PSRR")
    assert len(hits) == 1 and hits[0].doc_id == "d" and hits[0].page == 1


@pytest.mark.parametrize("use_fts5", [True, False])
def test_search_with_no_matches_returns_empty_list(tmp_path, use_fts5):
    _write(tmp_path, "d", 1, narrative="hello world")
    index = FullTextIndex(enriched_documents(tmp_path), use_fts5=use_fts5)
    assert index.search("nonexistent_term_xyz") == []


@pytest.mark.parametrize("use_fts5", [True, False])
def test_search_with_empty_query_returns_empty_list(tmp_path, use_fts5):
    _write(tmp_path, "d", 1, narrative="hello world")
    index = FullTextIndex(enriched_documents(tmp_path), use_fts5=use_fts5)
    assert index.search("   ") == []


def test_fts5_query_handles_punctuation_without_crashing(tmp_path):
    _write(tmp_path, "d", 1, narrative="some text")
    index = FullTextIndex(enriched_documents(tmp_path), use_fts5=True)
    assert index.search('weird: "query* AND (') == []
