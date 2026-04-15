# Knowledge Graph

ContextDB includes a triple-store knowledge graph backed by SQLite.
Each edge is a **(subject, predicate, object)** triple, optionally
carrying a numeric weight and arbitrary metadata.

---

## Adding triples

```python
db.add_triple("Alice",  "authored",   "Python Guide")
db.add_triple("Alice",  "authored",   "ML 101")
db.add_triple("Bob",    "authored",   "SQLite Handbook")
db.add_triple("Python Guide", "covers", "data science")

# With weight and metadata
db.add_triple("Alice", "knows", "Bob", weight=0.9,
              metadata={"since": 2020})
```

Inserting the same `(subject, predicate, object)` triple again **upserts**
the weight and metadata.

---

## Querying triples

Use `None` as a wildcard:

```python
# All triples where Alice is the subject
db.graph_query(subject="Alice")

# All "authored" edges
db.graph_query(predicate="authored")

# All triples pointing to "ML 101"
db.graph_query(obj="ML 101")

# Exact match
db.graph_query(subject="Alice", predicate="authored", obj="ML 101")
```

---

## Neighbours

```python
# Who did Alice author? (outgoing "authored" edges)
db.graph_neighbors("Alice", predicate="authored", direction="out")
# → ["ML 101", "Python Guide"]

# Who authored "ML 101"? (incoming edges)
db.graph_neighbors("ML 101", direction="in")
# → ["Alice"]

# Both directions
db.graph_neighbors("Alice", direction="both")
```

---

## BFS traversal

```python
tree = db.graph_traverse(
    "Alice",
    predicate=None,   # follow all edge types
    direction="out",
    max_depth=3,
)
# Returns: {"Alice": ["ML 101", "Python Guide"], "Python Guide": ["data science"], ...}
```

---

## Listing entities and predicates

```python
db.list_entities()    # sorted list of all subjects + objects
db.list_predicates()  # sorted list of all predicate types
```

---

## Removing triples

```python
db.remove_triple("Alice", "authored", "Python Guide")
```
