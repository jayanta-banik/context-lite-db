# context-lite-db

An AI-native local database that combines the simplicity of **SQLite** with
built-in support for **semantic search**, **knowledge graphs**, and
**retrieval-augmented generation (RAG)** – all in a single Python package with
no external infrastructure required.

---

## Features

| Capability | Description |
|---|---|
| **Relational** | Full SQLite access via a clean Python API (`create_table`, `insert`, `query`, `update`, `delete`, raw SQL) |
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

---

## Quick start

```python
from context_lite_db import ContextLiteDB

db = ContextLiteDB("mydb.db")           # or ":memory:" for tests
```

### Relational operations

```python
db.create_table("notes", {"title": "TEXT", "body": "TEXT"})

db.insert("notes", {"title": "Hello", "body": "World"})
db.insert("notes", {"title": "Goodbye", "body": "World"})

rows = db.query("SELECT * FROM notes WHERE title = ?", ["Hello"])
db.update("notes", {"title": "Hi"}, "title = ?", ["Hello"])
db.delete("notes", "title = ?", ["Hi"])

# Raw SQL is always available
db.execute("CREATE INDEX IF NOT EXISTS idx_body ON notes(body)")
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

db = ContextLiteDB("mydb.db",
                   embedding_provider="callable",
                   embedding_fn=openai_embed)
```

---

## API reference

### `ContextLiteDB(path, embedding_provider, embedding_model, embedding_fn)`

| Parameter | Default | Description |
|---|---|---|
| `path` | `":memory:"` | SQLite file path |
| `embedding_provider` | `"sentence-transformers"` | `"sentence-transformers"` or `"callable"` |
| `embedding_model` | `"all-MiniLM-L6-v2"` | Model name for sentence-transformers |
| `embedding_fn` | `None` | Custom `(str) -> list[float]` callable |

**Relational**: `execute`, `query`, `create_table`, `insert`, `update`, `delete`

**Semantic**: `add_document`, `semantic_search`, `delete_document`, `list_collections`

**Graph**: `add_triple`, `remove_triple`, `graph_query`, `graph_neighbors`, `graph_traverse`, `list_entities`, `list_predicates`

**RAG**: `db.rag.ingest`, `db.rag.retrieve`, `db.rag.build_context`, `db.rag.query`

---

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

---

## Project layout

```
context_lite_db/
├── __init__.py          # Public API surface
├── db.py                # ContextLiteDB – unified entry-point
├── embeddings.py        # EmbeddingProvider (sentence-transformers / callable)
├── vector_store.py      # VectorStore – SQLite-backed cosine-similarity search
├── knowledge_graph.py   # KnowledgeGraph – triple-store with BFS traversal
└── rag.py               # RAGEngine – chunk ingestion, retrieval, context assembly
tests/
examples/
    basic_usage.py
```

---

## License

MIT
