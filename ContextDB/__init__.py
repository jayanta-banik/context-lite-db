"""
ContextDB – top-level importable package.

Install with::

    pip install context-lite-db

Then use::

    import ContextDB
    db = ContextDB.ContextDB("mydb.db")

Or::

    from ContextDB import ContextDB
    db = ContextDB("mydb.db")

All public symbols from :mod:`context_lite_db` are re-exported here.
"""

from context_lite_db import (
    ContextDB,
    ContextLiteDB,
    EmbeddingProvider,
    KnowledgeGraph,
    RAGEngine,
    TableProxy,
    VectorStore,
    chunk_text,
)
from context_lite_db import __version__

__all__ = [
    "ContextDB",
    "ContextLiteDB",
    "EmbeddingProvider",
    "KnowledgeGraph",
    "RAGEngine",
    "TableProxy",
    "VectorStore",
    "chunk_text",
    "__version__",
]
