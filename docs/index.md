# ContextDB

**An AI-native local database that combines the simplicity of SQLite with
built-in support for semantic search, knowledge graphs, and
retrieval-augmented generation (RAG).**

---

## Why ContextDB?

Modern AI applications need more than a relational database, but not
everyone wants to run a vector database, a graph store, and a relational
database as three separate services.  **ContextDB** gives you all of that in
a single `.db` file with a clean Python API.

| Capability | Description |
|---|---|
| **Relational** | Full SQLite access + Prisma-style table attribute API |
| **Semantic search** | Cosine-similarity nearest-neighbour search |
| **Knowledge graph** | Triple-store with BFS traversal |
| **RAG** | Chunk ingestion, retrieval, context assembly, LLM integration |
| **Pluggable embeddings** | `sentence-transformers` or any callable |
| **Zero infrastructure** | One file, no external services |

---

## Installation

```bash
pip install context-lite-db
# Optional: built-in sentence-transformers embedding provider
pip install sentence-transformers
```

---

## Quick start

```python
from ContextDB import ContextDB

db = ContextDB("mydb.db")

# Prisma-style table access
db.create_table("notes", {"title": "TEXT", "body": "TEXT"})
db.notes.create({"title": "Hello", "body": "World"})
db.notes.find_all()

# Semantic search
db.add_document("doc1", "Python is great for data science")
results = db.semantic_search("programming language")

# Knowledge graph
db.add_triple("Alice", "authored", "Python Guide")
neighbors = db.graph_neighbors("Alice")

# RAG
db.rag.ingest("guide", open("guide.txt").read())
answer = db.rag.query("What is this guide about?", llm_fn=my_llm)
```

---

## Next steps

- [Getting Started](getting-started.md)
- [User Guide – Relational](guide/relational.md)
- [User Guide – Semantic Search](guide/semantic-search.md)
- [User Guide – Knowledge Graph](guide/knowledge-graph.md)
- [User Guide – RAG](guide/rag.md)
- [API Reference](api/context_db.md)
