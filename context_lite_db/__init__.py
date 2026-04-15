"""
context_lite_db – AI-native local database.

Combines the simplicity of SQLite with built-in support for semantic
search, knowledge graphs, and retrieval-augmented generation (RAG).

Quick start::

    from context_lite_db import ContextDB

    db = ContextDB("mydb.db")

    # Prisma-style table access
    db.create_table("notes", {"title": "TEXT", "body": "TEXT"})
    db.notes.create({"title": "Hello", "body": "World"})
    db.notes.find_all()

    # Semantic search
    db.add_document("doc1", "The quick brown fox jumps over the lazy dog")
    results = db.semantic_search("fast animal")

    # Knowledge graph
    db.add_triple("Alice", "wrote", "Hello World")
    db.add_triple("Hello World", "is_about", "greeting")
    neighbors = db.graph_neighbors("Alice", direction="out")

    # RAG
    db.rag.ingest("article1", "Long article text here …")
    context = db.rag.build_context("What is the article about?")
"""

from .db import ContextDB, ContextLiteDB
from .embeddings import EmbeddingProvider
from .knowledge_graph import KnowledgeGraph
from .rag import RAGEngine, chunk_text
from .table_proxy import TableProxy
from .vector_store import VectorStore

__all__ = [
    "ContextDB",
    "ContextLiteDB",
    "EmbeddingProvider",
    "KnowledgeGraph",
    "RAGEngine",
    "TableProxy",
    "VectorStore",
    "chunk_text",
]

__version__ = "0.1.0"
