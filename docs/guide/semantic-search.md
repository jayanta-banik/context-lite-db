# Semantic Search

ContextDB stores document embeddings as binary BLOBs inside SQLite and
retrieves them using cosine-similarity ranking – no external vector database
required.

---

## Adding documents

```python
db.add_document(
    doc_id="article_1",
    text="Python is a high-level programming language.",
    collection="articles",          # optional logical namespace
    metadata={"author": "Alice"},   # arbitrary JSON-serialisable dict
)
```

---

## Searching

```python
results = db.semantic_search(
    "programming language",
    top_k=5,               # maximum results
    collection="articles", # restrict to a collection (None = all)
    threshold=0.3,         # minimum cosine-similarity score
)

for r in results:
    print(r["score"], r["text"], r["metadata"])
```

Each result dict contains:

| Key | Description |
|---|---|
| `doc_id` | Application-level identifier |
| `text` | Original text |
| `score` | Cosine similarity (0–1) |
| `collection` | Collection name |
| `metadata` | Metadata dict or `None` |
| `created_at` | Unix timestamp |

---

## Collections

Use collections to partition documents into logical namespaces:

```python
db.add_document("d1", "...", collection="blog")
db.add_document("d2", "...", collection="wiki")

# List all collections
print(db.list_collections())  # ["blog", "wiki"]

# Search only within "blog"
results = db.semantic_search("query", collection="blog")
```

---

## Deleting documents

```python
db.delete_document("article_1", collection="articles")
```

---

## Custom embedding provider

```python
import openai

def openai_embed(text: str) -> list[float]:
    resp = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return resp.data[0].embedding

db = ContextDB(
    "mydb.db",
    embedding_provider="callable",
    embedding_fn=openai_embed,
)
```
