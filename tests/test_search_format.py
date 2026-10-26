import numpy as np
import pytest

from docparse.search.format import DimensionMismatch, EmbeddingIndex, EmbeddingItem


def make_items(doc_id, page, n, kind="page_text", start_row=0):
    return [EmbeddingItem(f"{doc_id}/{page}/{i}", doc_id, page, kind, start_row + i) for i in range(n)]


def test_empty_index_has_zero_dim_and_no_pages():
    idx = EmbeddingIndex()
    assert idx.dim == 0 and idx.doc_pages() == set()


def test_add_to_empty_index_sets_rows_from_zero():
    idx = EmbeddingIndex().add(make_items("d", 1, 2), np.zeros((2, 4), dtype=np.float32))
    assert idx.dim == 4
    assert [i.row for i in idx.items] == [0, 1]
    assert idx.doc_pages() == {("d", 1)}


def test_add_appends_and_renumbers_rows():
    idx = EmbeddingIndex().add(make_items("d", 1, 2), np.zeros((2, 4), dtype=np.float32))
    idx = idx.add(make_items("d", 2, 3), np.ones((3, 4), dtype=np.float32))
    assert idx.vectors.shape == (5, 4)
    assert [i.row for i in idx.items] == [0, 1, 2, 3, 4]
    assert idx.doc_pages() == {("d", 1), ("d", 2)}


def test_add_rejects_dimension_mismatch():
    idx = EmbeddingIndex().add(make_items("d", 1, 2), np.zeros((2, 4), dtype=np.float32))
    with pytest.raises(DimensionMismatch):
        idx.add(make_items("d", 2, 1), np.zeros((1, 8), dtype=np.float32))


def test_save_and_load_round_trip(tmp_path):
    idx = EmbeddingIndex().add(make_items("d", 1, 2), np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32))
    idx.save(tmp_path)
    loaded = EmbeddingIndex.load(tmp_path)
    assert loaded.dim == 2
    assert np.array_equal(loaded.vectors, idx.vectors)
    assert [(i.key, i.doc_id, i.page, i.kind, i.row) for i in loaded.items] == \
           [(i.key, i.doc_id, i.page, i.kind, i.row) for i in idx.items]


def test_load_missing_index_is_empty(tmp_path):
    assert EmbeddingIndex.load(tmp_path).dim == 0


def test_load_rejects_unexpected_dimension(tmp_path):
    idx = EmbeddingIndex().add(make_items("d", 1, 1), np.zeros((1, 4), dtype=np.float32))
    idx.save(tmp_path)
    with pytest.raises(DimensionMismatch):
        EmbeddingIndex.load(tmp_path, expected_dim=768)


def test_load_rejects_tampered_vectors_file(tmp_path):
    idx = EmbeddingIndex().add(make_items("d", 1, 1), np.zeros((1, 4), dtype=np.float32))
    idx.save(tmp_path)
    from docparse.search.format import vectors_path
    np.save(vectors_path(tmp_path), np.zeros((1, 8), dtype=np.float32))  # now disagrees with dim=4 in the JSON
    with pytest.raises(DimensionMismatch):
        EmbeddingIndex.load(tmp_path)
