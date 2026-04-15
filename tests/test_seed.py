"""Tests for db.seed(file_path) – file-based database seeding."""

import json
import os
import tempfile

import pytest

from context_lite_db import ContextDB, SeedResult, load_seed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db():
    return ContextDB(
        ":memory:",
        embedding_provider="callable",
        embedding_fn=lambda t: [0.1, 0.2, 0.3],
    )


def _write_seed(data: dict) -> str:
    """Write *data* to a temp JSON file; return its path."""
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, fh)
    fh.close()
    return fh.name


# ---------------------------------------------------------------------------
# SeedResult
# ---------------------------------------------------------------------------

class TestSeedResult:
    def test_initial_state(self):
        r = SeedResult()
        assert r.tables_created == []
        assert r.rows_inserted == {}
        assert r.triples_added == 0
        assert r.documents_added == 0

    def test_repr(self):
        r = SeedResult()
        assert "SeedResult" in repr(r)


# ---------------------------------------------------------------------------
# load_seed / db.seed – error handling
# ---------------------------------------------------------------------------

class TestSeedErrors:
    def test_file_not_found(self):
        db = _db()
        with pytest.raises(FileNotFoundError):
            db.seed("/nonexistent/path/seed.json")
        db.close()

    def test_missing_columns_key(self):
        path = _write_seed({"tables": {"users": {"rows": []}}})
        db = _db()
        try:
            with pytest.raises(ValueError, match="missing the 'columns' key"):
                db.seed(path)
        finally:
            os.unlink(path)
            db.close()

    def test_columns_must_be_dict(self):
        path = _write_seed({"tables": {"users": {"columns": ["name"]}}})
        db = _db()
        try:
            with pytest.raises(ValueError, match="must be a dict"):
                db.seed(path)
        finally:
            os.unlink(path)
            db.close()

    def test_triple_missing_subject(self):
        path = _write_seed({
            "triples": [{"predicate": "knows", "object": "Bob"}]
        })
        db = _db()
        try:
            with pytest.raises(ValueError, match="missing required key 'subject'"):
                db.seed(path)
        finally:
            os.unlink(path)
            db.close()

    def test_triple_missing_predicate(self):
        path = _write_seed({
            "triples": [{"subject": "Alice", "object": "Bob"}]
        })
        db = _db()
        try:
            with pytest.raises(ValueError, match="missing required key 'predicate'"):
                db.seed(path)
        finally:
            os.unlink(path)
            db.close()

    def test_triple_missing_object(self):
        path = _write_seed({
            "triples": [{"subject": "Alice", "predicate": "knows"}]
        })
        db = _db()
        try:
            with pytest.raises(ValueError, match="missing required key 'object'"):
                db.seed(path)
        finally:
            os.unlink(path)
            db.close()

    def test_document_missing_doc_id(self):
        path = _write_seed({"documents": [{"text": "hello"}]})
        db = _db()
        try:
            with pytest.raises(ValueError, match="missing required key 'doc_id'"):
                db.seed(path)
        finally:
            os.unlink(path)
            db.close()

    def test_document_missing_text(self):
        path = _write_seed({"documents": [{"doc_id": "d1"}]})
        db = _db()
        try:
            with pytest.raises(ValueError, match="missing required key 'text'"):
                db.seed(path)
        finally:
            os.unlink(path)
            db.close()


# ---------------------------------------------------------------------------
# Empty / minimal seeds
# ---------------------------------------------------------------------------

class TestEmptySeed:
    def test_empty_json_object(self):
        path = _write_seed({})
        db = _db()
        try:
            result = db.seed(path)
            assert result.tables_created == []
            assert result.rows_inserted == {}
            assert result.triples_added == 0
            assert result.documents_added == 0
        finally:
            os.unlink(path)
            db.close()


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

class TestSeedTables:
    def test_creates_table(self):
        path = _write_seed({
            "tables": {
                "products": {
                    "columns": {"name": "TEXT", "price": "REAL"}
                }
            }
        })
        db = _db()
        try:
            result = db.seed(path)
            assert "products" in result.tables_created
            rows = db.query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
            )
            assert len(rows) == 1
        finally:
            os.unlink(path)
            db.close()

    def test_creates_multiple_tables(self):
        path = _write_seed({
            "tables": {
                "users":  {"columns": {"name": "TEXT"}},
                "orders": {"columns": {"total": "REAL"}},
            }
        })
        db = _db()
        try:
            result = db.seed(path)
            assert set(result.tables_created) == {"users", "orders"}
        finally:
            os.unlink(path)
            db.close()

    def test_creates_table_with_rows(self):
        path = _write_seed({
            "tables": {
                "users": {
                    "columns": {"name": "TEXT"},
                    "rows": [{"name": "Alice"}, {"name": "Bob"}],
                }
            }
        })
        db = _db()
        try:
            result = db.seed(path)
            assert result.rows_inserted == {"users": 2}
            rows = db.query("SELECT name FROM users ORDER BY name")
            assert [r["name"] for r in rows] == ["Alice", "Bob"]
        finally:
            os.unlink(path)
            db.close()

    def test_no_rows_key_inserts_nothing(self):
        path = _write_seed({
            "tables": {"things": {"columns": {"val": "INTEGER"}}}
        })
        db = _db()
        try:
            result = db.seed(path)
            assert result.rows_inserted == {}
            assert db.query("SELECT * FROM things") == []
        finally:
            os.unlink(path)
            db.close()

    def test_if_not_exists_default_is_idempotent(self):
        seed = {
            "tables": {
                "items": {
                    "columns": {"name": "TEXT"},
                    "rows": [{"name": "first"}],
                }
            }
        }
        path = _write_seed(seed)
        db = _db()
        try:
            db.seed(path)
            db.seed(path)  # second call should not raise
            rows = db.query("SELECT name FROM items")
            assert len(rows) == 2  # rows were appended both times
        finally:
            os.unlink(path)
            db.close()

    def test_returns_seed_result_instance(self):
        path = _write_seed({
            "tables": {"x": {"columns": {"v": "TEXT"}}}
        })
        db = _db()
        try:
            result = db.seed(path)
            assert isinstance(result, SeedResult)
        finally:
            os.unlink(path)
            db.close()


# ---------------------------------------------------------------------------
# Knowledge-graph triples
# ---------------------------------------------------------------------------

class TestSeedTriples:
    def test_adds_triples(self):
        path = _write_seed({
            "triples": [
                {"subject": "Alice", "predicate": "knows", "object": "Bob"},
                {"subject": "Bob",   "predicate": "knows", "object": "Carol"},
            ]
        })
        db = _db()
        try:
            result = db.seed(path)
            assert result.triples_added == 2
            triples = db.graph_query(subject="Alice")
            assert len(triples) == 1
            assert triples[0]["object"] == "Bob"
        finally:
            os.unlink(path)
            db.close()

    def test_triple_with_weight_and_metadata(self):
        path = _write_seed({
            "triples": [
                {
                    "subject": "Alice",
                    "predicate": "authored",
                    "object": "ML Paper",
                    "weight": 0.8,
                    "metadata": {"year": 2024},
                }
            ]
        })
        db = _db()
        try:
            result = db.seed(path)
            assert result.triples_added == 1
            triples = db.graph_query(subject="Alice")
            assert triples[0]["weight"] == pytest.approx(0.8)
            assert triples[0]["metadata"]["year"] == 2024
        finally:
            os.unlink(path)
            db.close()

    def test_default_weight_is_one(self):
        path = _write_seed({
            "triples": [
                {"subject": "A", "predicate": "rel", "object": "B"}
            ]
        })
        db = _db()
        try:
            db.seed(path)
            triples = db.graph_query(subject="A")
            assert triples[0]["weight"] == pytest.approx(1.0)
        finally:
            os.unlink(path)
            db.close()


# ---------------------------------------------------------------------------
# Vector-store documents
# ---------------------------------------------------------------------------

class TestSeedDocuments:
    def test_adds_documents(self):
        path = _write_seed({
            "documents": [
                {"doc_id": "d1", "text": "hello world"},
                {"doc_id": "d2", "text": "foo bar"},
            ]
        })
        db = _db()
        try:
            result = db.seed(path)
            assert result.documents_added == 2
            hits = db.semantic_search("hello", top_k=5)
            doc_ids = [h["doc_id"] for h in hits]
            assert "d1" in doc_ids
        finally:
            os.unlink(path)
            db.close()

    def test_document_collection_and_metadata(self):
        path = _write_seed({
            "documents": [
                {
                    "doc_id": "d1",
                    "text": "Python is great",
                    "collection": "tech",
                    "metadata": {"author": "Alice"},
                }
            ]
        })
        db = _db()
        try:
            result = db.seed(path)
            assert result.documents_added == 1
            hits = db.semantic_search("Python", collection="tech")
            assert hits[0]["metadata"]["author"] == "Alice"
        finally:
            os.unlink(path)
            db.close()


# ---------------------------------------------------------------------------
# Combined seed (tables + triples + documents)
# ---------------------------------------------------------------------------

class TestSeedCombined:
    def test_full_seed(self):
        path = _write_seed({
            "tables": {
                "users": {
                    "columns": {"name": "TEXT", "role": "TEXT"},
                    "rows": [
                        {"name": "Alice", "role": "engineer"},
                        {"name": "Bob",   "role": "designer"},
                    ],
                }
            },
            "triples": [
                {"subject": "Alice", "predicate": "manages", "object": "Bob"}
            ],
            "documents": [
                {"doc_id": "bio_alice", "text": "Alice is a senior engineer."}
            ],
        })
        db = _db()
        try:
            result = db.seed(path)
            assert result.tables_created == ["users"]
            assert result.rows_inserted == {"users": 2}
            assert result.triples_added == 1
            assert result.documents_added == 1
            # verify data
            assert len(db.users.find_all()) == 2
            assert db.graph_neighbors("Alice") == ["Bob"]
            hits = db.semantic_search("engineer")
            assert any(h["doc_id"] == "bio_alice" for h in hits)
        finally:
            os.unlink(path)
            db.close()


# ---------------------------------------------------------------------------
# db.seed() convenience method (same as load_seed)
# ---------------------------------------------------------------------------

class TestDBSeedMethod:
    def test_db_seed_is_equivalent_to_load_seed(self):
        path = _write_seed({
            "tables": {"cats": {"columns": {"name": "TEXT"},
                                "rows": [{"name": "Whiskers"}]}}
        })
        db = _db()
        try:
            result = db.seed(path)
            assert "cats" in result.tables_created
            assert db.query("SELECT name FROM cats")[0]["name"] == "Whiskers"
        finally:
            os.unlink(path)
            db.close()
