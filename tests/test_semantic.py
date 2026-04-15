"""Tests for semantic / vector search."""

import math
import pytest
from context_lite_db import ContextLiteDB, EmbeddingProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _unit_vec(dims, index):
    """Return a unit vector with a 1.0 at *index*."""
    v = [0.0] * dims
    v[index] = 1.0
    return v


@pytest.fixture
def db():
    """DB wired to a deterministic 4-dim embedding function."""
    lookup = {
        "apple": _unit_vec(4, 0),
        "banana": _unit_vec(4, 1),
        "cherry": _unit_vec(4, 2),
        "date": _unit_vec(4, 3),
    }

    def embed(text: str):
        for key, vec in lookup.items():
            if key in text.lower():
                return vec
        return [0.25, 0.25, 0.25, 0.25]

    instance = ContextLiteDB(
        ":memory:",
        embedding_provider="callable",
        embedding_fn=embed,
    )
    yield instance
    instance.close()


# ---------------------------------------------------------------------------
# EmbeddingProvider
# ---------------------------------------------------------------------------

class TestEmbeddingProvider:
    def test_callable_provider(self):
        fn = lambda t: [1.0, 0.0, 0.0]
        ep = EmbeddingProvider(provider="callable", embedding_fn=fn)
        assert ep.encode("anything") == [1.0, 0.0, 0.0]

    def test_callable_batch(self):
        fn = lambda t: [len(t) / 100]
        ep = EmbeddingProvider(provider="callable", embedding_fn=fn)
        results = ep.encode_batch(["hi", "hello"])
        assert len(results) == 2

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError):
            EmbeddingProvider(provider="unknown")

    def test_callable_without_fn_raises(self):
        with pytest.raises(ValueError):
            EmbeddingProvider(provider="callable")


# ---------------------------------------------------------------------------
# add_document / semantic_search
# ---------------------------------------------------------------------------

class TestAddDocument:
    def test_returns_integer_id(self, db):
        row_id = db.add_document("doc1", "I like apple")
        assert isinstance(row_id, int)

    def test_metadata_is_stored(self, db):
        db.add_document("doc1", "apple", metadata={"author": "Alice"})
        from context_lite_db.vector_store import VectorStore
        rows = db._vectors.get("doc1")
        assert rows[0]["metadata"]["author"] == "Alice"

    def test_collection_is_stored(self, db):
        db.add_document("doc1", "apple", collection="fruits")
        rows = db._vectors.get("doc1", collection="fruits")
        assert len(rows) == 1


class TestSemanticSearch:
    def test_most_similar_returned_first(self, db):
        db.add_document("d_apple", "apple")
        db.add_document("d_banana", "banana")
        db.add_document("d_cherry", "cherry")

        # query embedding lands on apple's vector → d_apple should rank #1
        results = db.semantic_search("apple", top_k=3)
        assert results[0]["doc_id"] == "d_apple"

    def test_top_k_limits_results(self, db):
        for i in range(5):
            db.add_document(f"doc{i}", f"apple {i}")
        results = db.semantic_search("apple", top_k=3)
        assert len(results) <= 3

    def test_threshold_filters_results(self, db):
        db.add_document("d_apple", "apple")
        # query for banana with threshold 0.99 → apple (score ~0) excluded
        results = db.semantic_search("banana", threshold=0.99)
        doc_ids = [r["doc_id"] for r in results]
        assert "d_apple" not in doc_ids

    def test_collection_filter(self, db):
        db.add_document("d_apple", "apple", collection="A")
        db.add_document("d_banana", "banana", collection="B")
        results = db.semantic_search("apple", collection="A")
        assert all(r["collection"] == "A" for r in results)

    def test_score_field_present(self, db):
        db.add_document("d_apple", "apple")
        results = db.semantic_search("apple", top_k=1)
        assert "score" in results[0]
        assert 0.0 <= results[0]["score"] <= 1.001  # float tolerance


class TestDeleteDocument:
    def test_delete_removes_from_search(self, db):
        db.add_document("to_delete", "apple")
        db.delete_document("to_delete")
        results = db.semantic_search("apple")
        assert not any(r["doc_id"] == "to_delete" for r in results)


class TestListCollections:
    def test_lists_unique_collections(self, db):
        db.add_document("d1", "apple", collection="col_a")
        db.add_document("d2", "banana", collection="col_b")
        cols = db.list_collections()
        assert "col_a" in cols
        assert "col_b" in cols
