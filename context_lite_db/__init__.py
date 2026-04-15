"""
context_lite_db – AI-native local database.

Combines the simplicity of SQLite with built-in support for semantic
search, knowledge graphs, and retrieval-augmented generation (RAG).

Quick start::

    from context_lite_db import ContextLiteDB

    db = ContextLiteDB("mydb.db")

    # Traditional relational operations
    db.create_table("notes", {"title": "TEXT", "body": "TEXT"})
    db.insert("notes", {"title": "Hello", "body": "World"})
    rows = db.query("SELECT * FROM notes")

    # Semantic search
    db.add_document("doc1", "The quick brown fox jumps over the lazy dog")
    results = db.semantic_search("fast animal")

    # Knowledge graph
    db.add_triple("Alice", "wrote", "Hello World")
    db.add_triple("Hello World", "is_about", "greeting")
    neighbours = db.graph_neighbors("Alice", direction="out")

    # RAG
    db.rag.ingest("article1", "Long article text here …")
    context = db.rag.build_context("What is the article about?")
"""

from .db import ContextLiteDB
from .embeddings import EmbeddingProvider
from .knowledge_graph import KnowledgeGraph
from .rag import RAGEngine, chunk_text
from .vector_store import VectorStore

__all__ = [
    "ContextLiteDB",
    "EmbeddingProvider",
    "KnowledgeGraph",
    "RAGEngine",
    "VectorStore",
    "chunk_text",
]

__version__ = "0.1.0"
