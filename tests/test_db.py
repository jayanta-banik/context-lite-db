"""Tests for core relational database operations."""

import pytest
from context_lite_db import ContextLiteDB


@pytest.fixture
def db():
    """In-memory database with a dummy embedding function."""
    instance = ContextLiteDB(
        ":memory:",
        embedding_provider="callable",
        embedding_fn=lambda t: [float(ord(c)) / 1000 for c in t[:8].ljust(8)],
    )
    yield instance
    instance.close()


class TestCreateTable:
    def test_creates_table(self, db):
        db.create_table("items", {"name": "TEXT", "value": "REAL"})
        rows = db.query("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
        assert len(rows) == 1

    def test_if_not_exists_is_idempotent(self, db):
        db.create_table("items", {"name": "TEXT"})
        db.create_table("items", {"name": "TEXT"})  # should not raise


class TestInsert:
    def test_insert_returns_id(self, db):
        db.create_table("items", {"name": "TEXT"})
        row_id = db.insert("items", {"name": "alpha"})
        assert row_id == 1

    def test_insert_increments_id(self, db):
        db.create_table("items", {"name": "TEXT"})
        id1 = db.insert("items", {"name": "a"})
        id2 = db.insert("items", {"name": "b"})
        assert id2 == id1 + 1

    def test_inserted_row_is_queryable(self, db):
        db.create_table("items", {"name": "TEXT", "score": "REAL"})
        db.insert("items", {"name": "hello", "score": 42.0})
        rows = db.query("SELECT name, score FROM items")
        assert rows == [{"name": "hello", "score": 42.0}]


class TestQuery:
    def test_query_with_params(self, db):
        db.create_table("items", {"name": "TEXT", "tag": "TEXT"})
        db.insert("items", {"name": "alpha", "tag": "A"})
        db.insert("items", {"name": "beta", "tag": "B"})
        rows = db.query("SELECT name FROM items WHERE tag = ?", ["A"])
        assert rows == [{"name": "alpha"}]

    def test_empty_result(self, db):
        db.create_table("items", {"name": "TEXT"})
        rows = db.query("SELECT * FROM items WHERE name = ?", ["nonexistent"])
        assert rows == []


class TestUpdate:
    def test_update_modifies_row(self, db):
        db.create_table("items", {"name": "TEXT", "value": "INTEGER"})
        db.insert("items", {"name": "x", "value": 1})
        affected = db.update("items", {"value": 99}, "name = ?", ["x"])
        assert affected == 1
        rows = db.query("SELECT value FROM items WHERE name = ?", ["x"])
        assert rows[0]["value"] == 99

    def test_update_returns_zero_for_no_match(self, db):
        db.create_table("items", {"name": "TEXT"})
        affected = db.update("items", {"name": "y"}, "name = ?", ["missing"])
        assert affected == 0


class TestDelete:
    def test_delete_removes_row(self, db):
        db.create_table("items", {"name": "TEXT"})
        db.insert("items", {"name": "remove_me"})
        affected = db.delete("items", "name = ?", ["remove_me"])
        assert affected == 1
        rows = db.query("SELECT * FROM items")
        assert rows == []

    def test_delete_returns_zero_for_no_match(self, db):
        db.create_table("items", {"name": "TEXT"})
        affected = db.delete("items", "name = ?", ["ghost"])
        assert affected == 0


class TestExecute:
    def test_raw_execute(self, db):
        db.execute("CREATE TABLE raw_test (x INTEGER)")
        db.execute("INSERT INTO raw_test VALUES (?)", [42])
        rows = db.query("SELECT x FROM raw_test")
        assert rows == [{"x": 42}]


class TestContextManager:
    def test_context_manager(self):
        with ContextLiteDB(
            ":memory:",
            embedding_provider="callable",
            embedding_fn=lambda t: [0.1, 0.2],
        ) as db:
            db.create_table("t", {"v": "TEXT"})
            db.insert("t", {"v": "ok"})
            rows = db.query("SELECT v FROM t")
        assert rows == [{"v": "ok"}]
