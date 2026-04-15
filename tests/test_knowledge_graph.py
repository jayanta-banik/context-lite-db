"""Tests for knowledge graph operations."""

import pytest
from context_lite_db import ContextLiteDB


@pytest.fixture
def db():
    instance = ContextLiteDB(
        ":memory:",
        embedding_provider="callable",
        embedding_fn=lambda t: [0.0, 0.0],
    )
    yield instance
    instance.close()


class TestAddTriple:
    def test_returns_integer_id(self, db):
        row_id = db.add_triple("Alice", "knows", "Bob")
        assert isinstance(row_id, int)

    def test_triple_is_queryable(self, db):
        db.add_triple("Alice", "knows", "Bob")
        triples = db.graph_query(subject="Alice")
        assert len(triples) == 1
        assert triples[0]["predicate"] == "knows"
        assert triples[0]["object"] == "Bob"

    def test_upsert_updates_weight(self, db):
        db.add_triple("A", "rel", "B", weight=1.0)
        db.add_triple("A", "rel", "B", weight=5.0)
        triples = db.graph_query(subject="A", predicate="rel", obj="B")
        assert len(triples) == 1
        assert triples[0]["weight"] == 5.0

    def test_metadata_stored(self, db):
        db.add_triple("A", "rel", "B", metadata={"since": 2020})
        triples = db.graph_query(subject="A")
        assert triples[0]["metadata"]["since"] == 2020


class TestRemoveTriple:
    def test_remove_existing(self, db):
        db.add_triple("A", "rel", "B")
        removed = db.remove_triple("A", "rel", "B")
        assert removed is True
        assert db.graph_query(subject="A") == []

    def test_remove_nonexistent(self, db):
        removed = db.remove_triple("X", "rel", "Y")
        assert removed is False


class TestGraphQuery:
    def test_wildcard_subject(self, db):
        db.add_triple("Alice", "knows", "Bob")
        db.add_triple("Alice", "likes", "Chess")
        db.add_triple("Bob", "knows", "Carol")
        triples = db.graph_query(subject="Alice")
        assert len(triples) == 2

    def test_wildcard_predicate(self, db):
        db.add_triple("Alice", "knows", "Bob")
        db.add_triple("Carol", "knows", "Dave")
        triples = db.graph_query(predicate="knows")
        assert len(triples) == 2

    def test_wildcard_object(self, db):
        db.add_triple("Alice", "knows", "Bob")
        db.add_triple("Alice", "knows", "Carol")
        triples = db.graph_query(obj="Bob")
        assert len(triples) == 1

    def test_full_pattern(self, db):
        db.add_triple("A", "r", "B")
        db.add_triple("A", "r", "C")
        triples = db.graph_query(subject="A", predicate="r", obj="B")
        assert len(triples) == 1


class TestGraphNeighbors:
    def test_out_neighbors(self, db):
        db.add_triple("Alice", "knows", "Bob")
        db.add_triple("Alice", "knows", "Carol")
        nbrs = db.graph_neighbors("Alice", direction="out")
        assert sorted(nbrs) == ["Bob", "Carol"]

    def test_in_neighbors(self, db):
        db.add_triple("Alice", "knows", "Bob")
        db.add_triple("Carol", "knows", "Bob")
        nbrs = db.graph_neighbors("Bob", direction="in")
        assert sorted(nbrs) == ["Alice", "Carol"]

    def test_both_directions(self, db):
        db.add_triple("Alice", "knows", "Bob")
        db.add_triple("Carol", "knows", "Alice")
        nbrs = db.graph_neighbors("Alice", direction="both")
        assert "Bob" in nbrs
        assert "Carol" in nbrs

    def test_predicate_filter(self, db):
        db.add_triple("Alice", "knows", "Bob")
        db.add_triple("Alice", "likes", "Chess")
        nbrs = db.graph_neighbors("Alice", predicate="knows", direction="out")
        assert nbrs == ["Bob"]


class TestGraphTraverse:
    def test_bfs_returns_reachable(self, db):
        db.add_triple("A", "connects", "B")
        db.add_triple("B", "connects", "C")
        db.add_triple("C", "connects", "D")
        result = db.graph_traverse("A", max_depth=3)
        assert "B" in result or "B" in result.get("A", [])
        # A -> B -> C (depth 2) -> D (depth 3) should all be reachable
        all_entities = set(result.keys()) | {e for nbrs in result.values() for e in nbrs}
        assert "D" in all_entities

    def test_max_depth_limits(self, db):
        db.add_triple("A", "r", "B")
        db.add_triple("B", "r", "C")
        db.add_triple("C", "r", "D")
        result = db.graph_traverse("A", max_depth=1)
        # with max_depth=1 we should NOT expand B's neighbors
        assert "C" not in result


class TestListEntitiesPredicates:
    def test_list_entities(self, db):
        db.add_triple("Alice", "knows", "Bob")
        entities = db.list_entities()
        assert "Alice" in entities
        assert "Bob" in entities

    def test_list_predicates(self, db):
        db.add_triple("A", "knows", "B")
        db.add_triple("A", "likes", "C")
        preds = db.list_predicates()
        assert "knows" in preds
        assert "likes" in preds
