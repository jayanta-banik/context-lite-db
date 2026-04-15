# context-lite-db

An AI-native local database that combines the simplicity of **SQLite** with
built-in support for **semantic search**, **knowledge graphs**, and
**retrieval-augmented generation (RAG)** – all in a single Python package with
no external infrastructure required.

📚 **[Documentation](https://jayanta-banik.github.io/context-lite-db/)**

---

## Features

| Capability | Description |
|---|---|
| **Relational** | Full SQLite access + Prisma-style `db.table.create(...)` API |
| **Standalone core** | Rust-powered `contextdb` binary for bash, Python, and Node.js workflows |
| **Semantic search** | Store document embeddings as SQLite BLOBs; query by cosine similarity |
| **Knowledge graph** | Triple-store (subject / predicate / object) with BFS traversal |
| **RAG** | Chunk-and-embed ingestion, retrieval, context assembly, and end-to-end LLM integration |
| **Pluggable embeddings** | Use `sentence-transformers` out-of-the-box, or supply any `(text) -> list[float]` callable |
| **Zero infrastructure** | Everything lives in a single `.db` file (or `:memory:`) |

---

## Installation

```bash
pip install context-lite-db
# Optional: use the built-in sentence-transformers embedding provider
pip install sentence-transformers
```

```bash
cd packages/contextdb-js
npm install
```

The repository now includes:

- `contextdb` – the standalone Rust database/CLI
- `context-lite-db` – the Python client
- `packages/contextdb-js` – the Node.js client

---

## Quick start

```python
from ContextDB import ContextDB           # install: pip install context-lite-db

db = ContextDB("mydb.db")                 # or ":memory:" for tests
```

### Prisma-style table access

```python
db.create_table("notes", {"title": "TEXT", "body": "TEXT"})

# Create
db.notes.create({"title": "Hello", "body": "World"})

# Create many (single transaction)
db.notes.create_many([
    {"title": "Note 2", "body": "..."},
    {"title": "Note 3", "body": "..."},
])

# Seed a table with initial data
db.notes.seed_table([{"title": "Seed note", "body": "..."}])

# Read
all_notes = db.notes.find_all()
some_notes = db.notes.find_many("title LIKE ?", ["%Hello%"])
one_note   = db.notes.find_first("title = ?", ["Hello"])

# Update
db.notes.update({"body": "Updated"}, where="title = ?", params=["Hello"])

# Batch update (multiple WHERE clauses in one transaction)
db.notes.update_many([
    {"data": {"body": "A"}, "where": "title = ?", "params": ["Note 2"]},
    {"data": {"body": "B"}, "where": "title = ?", "params": ["Note 3"]},
])

# Delete
db.notes.delete("title = ?", ["Hello"])

# Batch delete
db.notes.delete_many([
    {"where": "title = ?", "params": ["Note 2"]},
    {"where": "title = ?", "params": ["Note 3"]},
])

# Table-level operations
db.notes.truncate()            # remove all rows, keep schema
db.notes.drop()                # drop the table
db.drop_table("notes")         # same, from DB level
db.truncate_table("notes")     # same, from DB level
db.seed_table("notes", [...])  # same, from DB level
```

### Prisma-inspired `context.schema`

```prisma
model notes {
  id        Int      @id
  title     String
  body      String?
  published Boolean  @default(false)
  createdAt DateTime @default(now())

  @@index([title], name: "idx_notes_title")
}
```

```python
from ContextDB import ContextDB

db = ContextDB("context.db", embedding_provider="callable", embedding_fn=lambda text: [0.0])
db.apply_schema("context.schema")
db.notes.create({"title": "Hello", "body": "World", "published": True})
```

### Bash / CLI access

```bash
cargo run --manifest-path crates/contextdb/Cargo.toml -- schema apply --db ./context.db --schema ./context.schema
cargo run --manifest-path crates/contextdb/Cargo.toml -- inspect --db ./context.db
cargo run --manifest-path crates/contextdb/Cargo.toml -- query --db ./context.db --sql "SELECT * FROM notes"
```

### Raw SQL (always available)

```python
rows = db.query("SELECT * FROM notes WHERE title = ?", ["Hello"])
db.insert("notes", {"title": "Hello", "body": "World"})
db.update("notes", {"title": "Hi"}, "title = ?", ["Hello"])
db.delete("notes", "title = ?", ["Hi"])
db.execute("CREATE INDEX IF NOT EXISTS idx_body ON notes(body)")
```

### Seed from a file

`db.seed(path)` reads a JSON (or YAML) file and creates tables, inserts rows,
adds knowledge-graph triples, and embeds documents in one declarative step:

```json
{
  "tables": {
    "users": {
      "columns": {"name": "TEXT", "role": "TEXT"},
      "rows": [
        {"name": "Alice", "role": "engineer"},
        {"name": "Bob",   "role": "designer"}
      ]
    }
  },
  "triples": [
    {"subject": "Alice", "predicate": "manages", "object": "Bob"}
  ],
  "documents": [
    {"doc_id": "bio_alice", "text": "Alice is a senior engineer.",
     "collection": "bios"}
  ]
}
```

```python
result = db.seed("seed.json")
print(result.tables_created)   # ["users"]
print(result.rows_inserted)    # {"users": 2}
print(result.triples_added)    # 1
print(result.documents_added)  # 1
```

### Semantic search

```python
db.add_document("doc1", "Python is a high-level programming language",
                metadata={"author": "Alice"})
db.add_document("doc2", "SQLite is a serverless embedded database")
db.add_document("doc3", "Machine learning is a subset of AI")

results = db.semantic_search("programming", top_k=2)
# [{"doc_id": "doc1", "text": "...", "score": 0.87, ...}, ...]

# Restrict to a named collection
db.add_document("d1", "text", collection="my_collection")
hits = db.semantic_search("text", collection="my_collection")
```

### Knowledge graph

```python
db.add_triple("Alice", "authored", "Python Guide")
db.add_triple("Python Guide", "covers", "data science")
db.add_triple("Bob",   "authored", "SQL Handbook")

# Pattern matching (None = wildcard)
triples = db.graph_query(subject="Alice")
triples = db.graph_query(predicate="authored")

# Direct neighbours
db.graph_neighbors("Alice", direction="out")  # ["Python Guide"]

# BFS traversal
tree = db.graph_traverse("Alice", max_depth=2)
# {"Alice": ["Python Guide"], "Python Guide": ["data science"]}

db.remove_triple("Alice", "authored", "Python Guide")
db.list_entities()
db.list_predicates()
```

### RAG (Retrieval-Augmented Generation)

```python
# Ingest a long document as overlapping chunks
db.rag.ingest("article1", open("article.txt").read(),
              chunk_size=512, overlap=64,
              metadata={"source": "article.txt"})

# Retrieve the most relevant chunks for a query
chunks = db.rag.retrieve("What is machine learning?", top_k=5)

# Build a ready-to-use context string
context = db.rag.build_context("What is machine learning?")

# End-to-end: retrieve + call any LLM
import openai

def call_openai(prompt: str) -> str:
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content

answer = db.rag.query("What is machine learning?", llm_fn=call_openai)
print(answer["answer"])
print(answer["sources"])   # list of retrieved chunks
```

### Custom embedding function

```python
import openai

def openai_embed(text: str) -> list[float]:
    resp = openai.embeddings.create(model="text-embedding-3-small", input=text)
    return resp.data[0].embedding

db = ContextDB("mydb.db",
               embedding_provider="callable",
               embedding_fn=openai_embed)
```

---

## API reference

### `ContextDB(path, embedding_provider, embedding_model, embedding_fn)`

| Parameter | Default | Description |
|---|---|---|
| `path` | `":memory:"` | SQLite file path |
| `embedding_provider` | `"sentence-transformers"` | `"sentence-transformers"` or `"callable"` |
| `embedding_model` | `"all-MiniLM-L6-v2"` | Model name for sentence-transformers |
| `embedding_fn` | `None` | Custom `(str) -> list[float]` callable |

**Prisma-style**: `db.<table>.create`, `create_many`, `find_all`, `find_many`, `find_first`, `update`, `update_many`, `delete`, `delete_many`, `truncate`, `drop`, `seed_table`

**Relational**: `execute`, `query`, `create_table`, `insert`, `update`, `delete`, `drop_table`, `truncate_table`, `seed_table`

**Seed from file**: `db.seed(path)` → `SeedResult`

**Semantic**: `add_document`, `semantic_search`, `delete_document`, `list_collections`

**Graph**: `add_triple`, `remove_triple`, `graph_query`, `graph_neighbors`, `graph_traverse`, `list_entities`, `list_predicates`

**RAG**: `db.rag.ingest`, `db.rag.retrieve`, `db.rag.build_context`, `db.rag.query`

> Full API docs: <https://jayanta-banik.github.io/context-lite-db/>

---

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

---

## Project layout

```
ContextDB/
└── __init__.py          # Top-level importable package (import ContextDB)
context_lite_db/
├── __init__.py          # Public API surface
├── db.py                # ContextDB – unified entry-point
├── embeddings.py        # EmbeddingProvider (sentence-transformers / callable)
├── table_proxy.py       # TableProxy – Prisma-style table CRUD
├── vector_store.py      # VectorStore – SQLite-backed cosine-similarity search
├── knowledge_graph.py   # KnowledgeGraph – triple-store with BFS traversal
└── rag.py               # RAGEngine – chunk ingestion, retrieval, context assembly
docs/                    # MkDocs source → GitHub Pages
tests/
examples/
    basic_usage.py
```

---

## License

MIT
