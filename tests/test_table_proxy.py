"""Tests for TableProxy (Prisma-style CRUD) and the ContextDB import."""

import pytest
from context_lite_db import ContextDB, ContextLiteDB
from context_lite_db.table_proxy import TableProxy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    instance = ContextDB(
        ":memory:",
        embedding_provider="callable",
        embedding_fn=lambda t: [0.1, 0.2],
    )
    instance.create_table("users", {"name": "TEXT", "score": "INTEGER"})
    yield instance
    instance.close()


# ---------------------------------------------------------------------------
# Import / naming
# ---------------------------------------------------------------------------

class TestImport:
    def test_contextdb_importable_from_context_lite_db(self):
        from context_lite_db import ContextDB
        assert ContextDB is not None

    def test_contextlitedb_is_alias(self):
        assert ContextLiteDB is ContextDB

    def test_import_from_ContextDB_package(self):
        from ContextDB import ContextDB as CDB
        assert CDB is ContextDB

    def test_contextdb_instantiable(self):
        db = ContextDB(":memory:", embedding_provider="callable",
                       embedding_fn=lambda t: [0.0])
        db.close()


# ---------------------------------------------------------------------------
# Attribute access / TableProxy creation
# ---------------------------------------------------------------------------

class TestAttributeAccess:
    def test_attribute_returns_table_proxy(self, db):
        proxy = db.users
        assert isinstance(proxy, TableProxy)

    def test_proxy_table_name(self, db):
        proxy = db.users
        assert proxy._table == "users"

    def test_private_attribute_raises(self, db):
        with pytest.raises(AttributeError):
            _ = db._nonexistent_private

    def test_existing_method_not_shadowed(self, db):
        # create_table is a real method, not a TableProxy
        assert callable(db.create_table)

    def test_rag_property_not_shadowed(self, db):
        from context_lite_db.rag import RAGEngine
        assert isinstance(db.rag, RAGEngine)


# ---------------------------------------------------------------------------
# TableProxy.create / create_many / seed_table
# ---------------------------------------------------------------------------

class TestCreate:
    def test_create_returns_id(self, db):
        row_id = db.users.create({"name": "Alice", "score": 10})
        assert isinstance(row_id, int)

    def test_create_row_is_findable(self, db):
        db.users.create({"name": "Bob", "score": 20})
        rows = db.users.find_all()
        names = [r["name"] for r in rows]
        assert "Bob" in names

    def test_create_many_returns_ids(self, db):
        ids = db.users.create_many([
            {"name": "Alice", "score": 1},
            {"name": "Bob", "score": 2},
            {"name": "Carol", "score": 3},
        ])
        assert len(ids) == 3
        assert all(isinstance(i, int) for i in ids)

    def test_create_many_all_inserted(self, db):
        db.users.create_many([
            {"name": "X", "score": 10},
            {"name": "Y", "score": 20},
        ])
        rows = db.users.find_all()
        assert len(rows) == 2

    def test_seed_table_is_alias_for_create_many(self, db):
        ids = db.users.seed_table([
            {"name": "S1", "score": 100},
            {"name": "S2", "score": 200},
        ])
        assert len(ids) == 2
        rows = db.users.find_all()
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# TableProxy.find_all / find_many / find_first
# ---------------------------------------------------------------------------

class TestFind:
    def test_find_all_empty(self, db):
        assert db.users.find_all() == []

    def test_find_all_returns_rows(self, db):
        db.users.create({"name": "Alice", "score": 5})
        db.users.create({"name": "Bob", "score": 10})
        rows = db.users.find_all()
        assert len(rows) == 2

    def test_find_many_filters(self, db):
        db.users.create({"name": "Alice", "score": 5})
        db.users.create({"name": "Bob", "score": 10})
        rows = db.users.find_many("score > ?", [7])
        assert len(rows) == 1
        assert rows[0]["name"] == "Bob"

    def test_find_first_returns_one(self, db):
        db.users.create({"name": "Alice", "score": 5})
        db.users.create({"name": "Bob", "score": 10})
        row = db.users.find_first("score > ?", [0])
        assert row is not None
        assert "name" in row

    def test_find_first_returns_none_when_no_match(self, db):
        row = db.users.find_first("name = ?", ["Ghost"])
        assert row is None


# ---------------------------------------------------------------------------
# TableProxy.update / update_many
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_update_modifies_row(self, db):
        db.users.create({"name": "Alice", "score": 5})
        affected = db.users.update({"score": 99}, "name = ?", ["Alice"])
        assert affected == 1
        row = db.users.find_first("name = ?", ["Alice"])
        assert row["score"] == 99

    def test_update_returns_zero_for_no_match(self, db):
        affected = db.users.update({"score": 1}, "name = ?", ["Ghost"])
        assert affected == 0

    def test_update_many_applies_all(self, db):
        db.users.create({"name": "Alice", "score": 1})
        db.users.create({"name": "Bob", "score": 2})
        total = db.users.update_many([
            {"data": {"score": 100}, "where": "name = ?", "params": ["Alice"]},
            {"data": {"score": 200}, "where": "name = ?", "params": ["Bob"]},
        ])
        assert total == 2
        alice = db.users.find_first("name = ?", ["Alice"])
        bob = db.users.find_first("name = ?", ["Bob"])
        assert alice["score"] == 100
        assert bob["score"] == 200

    def test_update_many_returns_total_count(self, db):
        db.users.create({"name": "Alice", "score": 1})
        total = db.users.update_many([
            {"data": {"score": 50}, "where": "name = ?", "params": ["Alice"]},
            {"data": {"score": 50}, "where": "name = ?", "params": ["Ghost"]},
        ])
        assert total == 1  # only Alice matched


# ---------------------------------------------------------------------------
# TableProxy.delete / delete_many
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_removes_row(self, db):
        db.users.create({"name": "Alice", "score": 1})
        affected = db.users.delete("name = ?", ["Alice"])
        assert affected == 1
        assert db.users.find_all() == []

    def test_delete_returns_zero_for_no_match(self, db):
        affected = db.users.delete("name = ?", ["Ghost"])
        assert affected == 0

    def test_delete_many_applies_all(self, db):
        db.users.create({"name": "Alice", "score": 1})
        db.users.create({"name": "Bob", "score": 2})
        total = db.users.delete_many([
            {"where": "name = ?", "params": ["Alice"]},
            {"where": "name = ?", "params": ["Bob"]},
        ])
        assert total == 2
        assert db.users.find_all() == []


# ---------------------------------------------------------------------------
# TableProxy.drop / truncate
# ---------------------------------------------------------------------------

class TestDropTruncate:
    def test_truncate_removes_all_rows(self, db):
        db.users.create({"name": "Alice", "score": 1})
        db.users.truncate()
        assert db.users.find_all() == []

    def test_truncate_preserves_schema(self, db):
        db.users.create({"name": "Alice", "score": 1})
        db.users.truncate()
        # Should still be able to insert after truncate
        db.users.create({"name": "New", "score": 99})
        assert len(db.users.find_all()) == 1

    def test_drop_removes_table(self, db):
        db.users.drop()
        rows = db.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        assert rows == []

    def test_drop_is_idempotent(self, db):
        db.users.drop()
        db.users.drop()  # should not raise


# ---------------------------------------------------------------------------
# DB-level table helpers: drop_table / truncate_table / seed_table
# ---------------------------------------------------------------------------

class TestDBTableHelpers:
    def test_drop_table(self, db):
        db.drop_table("users")
        rows = db.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        assert rows == []

    def test_truncate_table(self, db):
        db.users.create({"name": "Alice", "score": 1})
        db.truncate_table("users")
        assert db.users.find_all() == []

    def test_seed_table(self, db):
        ids = db.seed_table("users", [
            {"name": "A", "score": 1},
            {"name": "B", "score": 2},
        ])
        assert len(ids) == 2
        assert len(db.users.find_all()) == 2
