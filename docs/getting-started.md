# Getting Started

## Installation

```bash
pip install context-lite-db
```

For the standalone Rust/CLI engine from this repository:

```bash
cargo build --manifest-path /home/runner/work/context-lite-db/context-lite-db/crates/contextdb/Cargo.toml --release --target-dir /home/runner/work/context-lite-db/context-lite-db/target
```

For the built-in `sentence-transformers` embedding provider (downloads a
small model on first use):

```bash
pip install "context-lite-db[sentence-transformers]"
```

---

## Opening a database

```python
from ContextDB import ContextDB

# Persistent file
db = ContextDB("mydb.db")

# In-memory (great for tests)
db = ContextDB(":memory:")

# Custom embedding function (no model download required)
db = ContextDB(
    "mydb.db",
    embedding_provider="callable",
    embedding_fn=lambda text: my_embed_api(text),
)
```

---

## Your first database

```python
from ContextDB import ContextDB

db = ContextDB("quickstart.db")

# 1 – Create a table
db.create_table("articles", {
    "title": "TEXT",
    "body":  "TEXT",
    "author": "TEXT",
})

# 2 – Insert rows (Prisma-style)
db.articles.create({"title": "Intro to Python", "body": "Python is a high-level language.", "author": "Alice"})
db.articles.create({"title": "SQLite Guide",    "body": "SQLite is a serverless database.",  "author": "Bob"})

# 3 – Seed with multiple rows at once
db.articles.seed_table([
    {"title": "ML 101",    "body": "ML is a subset of AI.",        "author": "Alice"},
    {"title": "Deep Dive", "body": "Neural networks are powerful.", "author": "Carol"},
])

# 4 – Semantic search
for row in db.articles.find_all():
    db.add_document(f"article_{row['id']}", row["body"],
                    collection="articles", metadata={"title": row["title"]})

results = db.semantic_search("programming language", top_k=2, collection="articles")
for r in results:
    print(f"[{r['score']:.3f}] {r['metadata']['title']}")

# 5 – Knowledge graph
db.add_triple("Alice", "authored", "Intro to Python")
db.add_triple("Alice", "authored", "ML 101")
print("Alice authored:", [t["object"] for t in db.graph_query(subject="Alice")])

# 6 – RAG
db.rag.ingest("python_doc", "Python is widely used in data science and AI …",
              chunk_size=200, overlap=40)
ctx = db.rag.build_context("What is Python used for?")
print(ctx[:200])

db.close()
```

## Applying `context.schema`

```prisma
model articles {
  id        Int      @id
  title     String
  body      String?
  author    String
  createdAt DateTime @default(now())
}
```

```python
from ContextDB import ContextDB

db = ContextDB("schema-first.db", embedding_provider="callable", embedding_fn=lambda text: [0.0])
db.apply_schema("context.schema")
db.articles.create({"title": "Hello", "body": "World", "author": "Alice"})
```

---

## Next steps

- [Relational operations →](guide/relational.md)
- [Semantic search →](guide/semantic-search.md)
- [Knowledge graph →](guide/knowledge-graph.md)
- [RAG →](guide/rag.md)
