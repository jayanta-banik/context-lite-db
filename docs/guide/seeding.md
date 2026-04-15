# Seeding the Database

`db.seed(path)` lets you define your entire initial database state – tables,
rows, knowledge-graph triples, and vector-store documents – in a single
declarative file.  The file is read once and applied atomically in the order:
tables → rows → triples → documents.

---

## Seed file format

The seed file is a JSON (or YAML, if PyYAML is installed) object with the
following optional top-level keys.

```json
{
  "tables": {
    "<table_name>": {
      "columns": { "<col>": "<SQLite type>", ... },
      "rows": [ { "<col>": <value>, ... }, ... ],
      "if_not_exists": true
    }
  },
  "triples": [
    {
      "subject":   "<entity>",
      "predicate": "<relationship>",
      "object":    "<entity>",
      "weight":    1.0,
      "metadata":  { ... }
    }
  ],
  "documents": [
    {
      "doc_id":     "<id>",
      "text":       "<content to embed>",
      "collection": "default",
      "metadata":   { ... }
    }
  ]
}
```

| Key | Required | Description |
|---|---|---|
| `tables.<name>.columns` | yes | Column → SQLite type mapping |
| `tables.<name>.rows` | no | Rows to insert after table creation |
| `tables.<name>.if_not_exists` | no (default `true`) | Skip creation if table exists |
| `triples[].subject` | yes | Triple subject entity |
| `triples[].predicate` | yes | Relationship type |
| `triples[].object` | yes | Triple object entity |
| `triples[].weight` | no (default `1.0`) | Edge weight |
| `triples[].metadata` | no | Arbitrary JSON metadata |
| `documents[].doc_id` | yes | Document identifier |
| `documents[].text` | yes | Text to embed and store |
| `documents[].collection` | no (default `"default"`) | Vector-store collection |
| `documents[].metadata` | no | Arbitrary JSON metadata |

---

## Example seed file

```json
{
  "tables": {
    "users": {
      "columns": { "name": "TEXT", "role": "TEXT" },
      "rows": [
        { "name": "Alice", "role": "engineer" },
        { "name": "Bob",   "role": "designer" }
      ]
    },
    "projects": {
      "columns": { "title": "TEXT", "status": "TEXT" },
      "rows": [
        { "title": "Alpha", "status": "active" }
      ]
    }
  },
  "triples": [
    { "subject": "Alice", "predicate": "owns",    "object": "Alpha" },
    { "subject": "Alice", "predicate": "manages", "object": "Bob"   }
  ],
  "documents": [
    {
      "doc_id": "bio_alice",
      "text": "Alice is a senior engineer who owns the Alpha project.",
      "collection": "bios",
      "metadata": { "department": "engineering" }
    }
  ]
}
```

---

## Applying the seed

```python
from ContextDB import ContextDB

db = ContextDB("mydb.db")
result = db.seed("seed.json")

print(result.tables_created)   # ["users", "projects"]
print(result.rows_inserted)    # {"users": 2, "projects": 1}
print(result.triples_added)    # 2
print(result.documents_added)  # 1
```

---

## Using YAML

Install PyYAML and use a `.yaml` or `.yml` extension:

```bash
pip install pyyaml
```

```yaml
tables:
  users:
    columns:
      name: TEXT
      role: TEXT
    rows:
      - name: Alice
        role: engineer
      - name: Bob
        role: designer
triples:
  - subject: Alice
    predicate: manages
    object: Bob
documents:
  - doc_id: bio_alice
    text: Alice is a senior engineer.
    collection: bios
```

```python
result = db.seed("seed.yaml")
```

---

## Idempotency

By default `if_not_exists: true` means table creation is idempotent.
Row insertion is **not** deduplicated, so running `db.seed()` twice will
insert rows twice.  To seed only a fresh database, guard with a check:

```python
if db.query("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table'")[0]["n"] == 0:
    db.seed("seed.json")
```
