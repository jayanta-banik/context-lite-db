"""
Basic usage example for context-lite-db.

Run with:
    python examples/basic_usage.py

This example uses the built-in sentence-transformers embedding back-end.
To avoid downloading a model, it falls back to a simple callable when
sentence-transformers is not available.
"""

from context_lite_db import ContextLiteDB

# ---------------------------------------------------------------------------
# 1. Open the database
# ---------------------------------------------------------------------------

db = ContextLiteDB(
    "example.db",
    embedding_provider="sentence-transformers",
    embedding_model="all-MiniLM-L6-v2",
)

print("=" * 60)
print("context-lite-db – basic usage example")
print("=" * 60)

# ---------------------------------------------------------------------------
# 2. Relational operations
# ---------------------------------------------------------------------------

print("\n--- Relational operations ---")
db.create_table("articles", {"title": "TEXT", "body": "TEXT", "author": "TEXT"})

db.insert("articles", {"title": "Intro to Python", "body": "Python is a high-level programming language.", "author": "Alice"})
db.insert("articles", {"title": "SQLite Guide", "body": "SQLite is a serverless embedded database.", "author": "Bob"})
db.insert("articles", {"title": "Machine Learning 101", "body": "ML is a subset of artificial intelligence.", "author": "Alice"})

rows = db.query("SELECT title, author FROM articles WHERE author = ?", ["Alice"])
print("Articles by Alice:", [r["title"] for r in rows])

db.update("articles", {"author": "Dr. Alice"}, "author = ?", ["Alice"])
updated = db.query("SELECT title, author FROM articles WHERE author = 'Dr. Alice'")
print("After update:", [r["author"] for r in updated])

# ---------------------------------------------------------------------------
# 3. Semantic search
# ---------------------------------------------------------------------------

print("\n--- Semantic search ---")
for row in db.query("SELECT id, title, body FROM articles"):
    db.add_document(
        doc_id=f"article_{row['id']}",
        text=row["body"],
        collection="articles",
        metadata={"title": row["title"]},
    )

results = db.semantic_search("programming language", top_k=2, collection="articles")
print("Most relevant to 'programming language':")
for r in results:
    print(f"  [{r['score']:.3f}] {r['metadata']['title']}")

# ---------------------------------------------------------------------------
# 4. Knowledge graph
# ---------------------------------------------------------------------------

print("\n--- Knowledge graph ---")
db.add_triple("Alice", "authored", "Intro to Python")
db.add_triple("Alice", "authored", "Machine Learning 101")
db.add_triple("Bob", "authored", "SQLite Guide")
db.add_triple("Python", "is_a", "programming language")
db.add_triple("SQLite", "is_a", "database")
db.add_triple("Machine Learning", "is_part_of", "Artificial Intelligence")

authored = db.graph_query(subject="Alice", predicate="authored")
print("Alice authored:", [t["object"] for t in authored])

neighbors = db.graph_neighbors("Alice", direction="out")
print("Alice's out-neighbors:", neighbors)

traversal = db.graph_traverse("Alice", max_depth=2)
print("BFS from Alice:", traversal)

# ---------------------------------------------------------------------------
# 5. RAG – ingest, retrieve, build context, end-to-end
# ---------------------------------------------------------------------------

print("\n--- RAG ---")
long_text = (
    "Python is a versatile programming language widely used in data science, "
    "web development, automation, and artificial intelligence. "
    "It emphasises code readability and supports multiple programming paradigms. "
    "Python's rich ecosystem of libraries — such as NumPy, Pandas, and scikit-learn — "
    "makes it the language of choice for machine learning practitioners. "
)

db.rag.ingest("python_overview", long_text, collection="docs", chunk_size=200, overlap=50)

context = db.rag.build_context("What is Python used for?", collection="docs")
print("Retrieved context (first 300 chars):")
print(context[:300], "...\n")

# Simulate an LLM that just echoes the context (replace with a real LLM call)
def mock_llm(prompt: str) -> str:
    return "Python is a high-level language great for AI and data science."

answer = db.rag.query(
    "What is Python used for?",
    llm_fn=mock_llm,
    collection="docs",
)
print("RAG answer:", answer["answer"])
print("Number of source chunks retrieved:", len(answer["sources"]))

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

db.close()

import os
if os.path.exists("example.db"):
    os.remove("example.db")

print("\nDone.")
