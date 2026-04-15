"""
context_lite_db – core database module.

:class:`ContextLiteDB` is the single entry-point for all operations:

* **Relational** – plain SQL via ``execute`` / ``query``, plus convenience
  helpers ``create_table``, ``insert``, ``update``, ``delete``.
* **Semantic search** – ``add_document`` + ``semantic_search``.
* **Knowledge graph** – ``add_triple``, ``remove_triple``, ``graph_query``,
  ``graph_traverse``.
* **RAG** – ``rag`` property returns a :class:`~context_lite_db.rag.RAGEngine`
  pre-wired to this database instance.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .embeddings import EmbeddingProvider
from .knowledge_graph import KnowledgeGraph
from .rag import RAGEngine
from .vector_store import VectorStore


class ContextLiteDB:
    """AI-native local database combining SQLite, semantic search, knowledge
    graphs, and RAG in a single file-based store.

    Parameters
    ----------
    path:
        Path to the SQLite database file.  Use ``":memory:"`` for an
        in-memory database (useful for testing).
    embedding_provider:
        Which embedding back-end to use.  ``"sentence-transformers"``
        (default) downloads a small model on first use; ``"callable"``
        delegates to *embedding_fn*.
    embedding_model:
        Model name forwarded to sentence-transformers.
    embedding_fn:
        Custom callable ``(text: str) -> list[float]`` used when
        *embedding_provider* is ``"callable"``.

    Examples
    --------
    >>> db = ContextLiteDB(":memory:", embedding_provider="callable",
    ...                    embedding_fn=lambda t: [0.0] * 8)
    >>> db.create_table("notes", {"title": "TEXT", "body": "TEXT"})
    >>> db.insert("notes", {"title": "Hello", "body": "World"})
    >>> db.add_triple("Alice", "wrote", "Hello")
    >>> db.add_document("doc1", "Hello World", metadata={"author": "Alice"})
    >>> results = db.semantic_search("greeting")
    """

    def __init__(
        self,
        path: str = ":memory:",
        embedding_provider: str = "sentence-transformers",
        embedding_model: str = "all-MiniLM-L6-v2",
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
    ) -> None:
        self._path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        self._embedder = EmbeddingProvider(
            provider=embedding_provider,
            model_name=embedding_model,
            embedding_fn=embedding_fn,
        )
        self._vectors = VectorStore(self._conn)
        self._graph = KnowledgeGraph(self._conn)
        self._rag_engine: Optional[RAGEngine] = None

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "ContextLiteDB":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Relational helpers
    # ------------------------------------------------------------------

    def execute(
        self, sql: str, params: Union[List, Tuple, None] = None
    ) -> sqlite3.Cursor:
        """Execute raw SQL and return the cursor.

        Automatically commits for DML/DDL statements.
        """
        cur = self._conn.execute(sql, params or [])
        if sql.strip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")):
            self._conn.commit()
        return cur

    def query(
        self, sql: str, params: Union[List, Tuple, None] = None
    ) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results as a list of dicts."""
        cur = self._conn.execute(sql, params or [])
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def create_table(
        self,
        table: str,
        columns: Dict[str, str],
        if_not_exists: bool = True,
    ) -> None:
        """Create a table with the specified column definitions.

        Parameters
        ----------
        table:
            Table name.
        columns:
            Mapping of ``column_name -> SQLite type`` (e.g. ``"TEXT"``,
            ``"INTEGER"``, ``"REAL"``).  An ``id INTEGER PRIMARY KEY
            AUTOINCREMENT`` column is added automatically.
        if_not_exists:
            Silently skip if the table already exists.
        """
        col_defs = ", ".join(f"{name} {dtype}" for name, dtype in columns.items())
        guard = "IF NOT EXISTS " if if_not_exists else ""
        self._conn.execute(
            f"CREATE TABLE {guard}{table} "
            f"(id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs})"
        )
        self._conn.commit()

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """Insert a row and return the new row *id*."""
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        cur = self._conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def update(
        self,
        table: str,
        data: Dict[str, Any],
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> int:
        """Update rows matching *where* with values in *data*.

        Returns the number of rows affected.
        """
        set_clause = ", ".join(f"{k} = ?" for k in data.keys())
        all_params = list(data.values()) + list(params or [])
        cur = self._conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE {where}",
            all_params,
        )
        self._conn.commit()
        return cur.rowcount

    def delete(
        self,
        table: str,
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> int:
        """Delete rows matching *where*.  Returns the number of rows deleted."""
        cur = self._conn.execute(
            f"DELETE FROM {table} WHERE {where}",
            params or [],
        )
        self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Semantic / vector search
    # ------------------------------------------------------------------

    def add_document(
        self,
        doc_id: str,
        text: str,
        collection: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Embed *text* and store it in the vector store.

        Parameters
        ----------
        doc_id:
            Application-level identifier for this document.
        text:
            Text to embed and store.
        collection:
            Logical group for this document.
        metadata:
            Arbitrary JSON-serialisable metadata.

        Returns
        -------
        int
            The row id in the internal vector table.
        """
        embedding = self._embedder.encode(text)
        return self._vectors.add(
            doc_id=doc_id,
            text=text,
            embedding=embedding,
            collection=collection,
            metadata=metadata,
        )

    def semantic_search(
        self,
        query: str,
        top_k: int = 5,
        collection: Optional[str] = None,
        threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Find the *top_k* most semantically similar documents to *query*.

        Parameters
        ----------
        query:
            Natural-language query string.
        top_k:
            Maximum number of results.
        collection:
            Restrict search to this collection (``None`` = all).
        threshold:
            Minimum cosine-similarity score.

        Returns
        -------
        list[dict]
            Each dict contains ``doc_id``, ``text``, ``score``,
            ``collection``, ``metadata``, and ``created_at``.
        """
        query_embedding = self._embedder.encode(query)
        return self._vectors.search(
            query_embedding=query_embedding,
            top_k=top_k,
            collection=collection,
            threshold=threshold,
        )

    def delete_document(self, doc_id: str, collection: str = "default") -> int:
        """Remove a document from the vector store."""
        return self._vectors.delete(doc_id=doc_id, collection=collection)

    def list_collections(self) -> List[str]:
        """List all vector-store collections."""
        return self._vectors.list_collections()

    # ------------------------------------------------------------------
    # Knowledge graph
    # ------------------------------------------------------------------

    def add_triple(
        self,
        subject: str,
        predicate: str,
        obj: str,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Add or update a (subject, predicate, object) triple.

        Returns the row *id*.
        """
        return self._graph.add_triple(
            subject=subject,
            predicate=predicate,
            obj=obj,
            weight=weight,
            metadata=metadata,
        )

    def remove_triple(self, subject: str, predicate: str, obj: str) -> bool:
        """Delete a specific triple.  Returns ``True`` if it existed."""
        return self._graph.remove_triple(subject, predicate, obj)

    def graph_query(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Flexible triple-pattern query (wildcards via ``None``)."""
        return self._graph.query(subject=subject, predicate=predicate, obj=obj)

    def graph_neighbors(
        self,
        entity: str,
        predicate: Optional[str] = None,
        direction: str = "out",
    ) -> List[str]:
        """Return direct neighbours of *entity* in the knowledge graph."""
        return self._graph.neighbors(
            entity=entity, predicate=predicate, direction=direction
        )

    def graph_traverse(
        self,
        start: str,
        predicate: Optional[str] = None,
        direction: str = "out",
        max_depth: int = 3,
    ) -> Dict[str, List[str]]:
        """BFS traversal from *start* returning an adjacency dict."""
        return self._graph.traverse(
            start=start,
            predicate=predicate,
            direction=direction,
            max_depth=max_depth,
        )

    def list_entities(self) -> List[str]:
        """Return all entities in the knowledge graph."""
        return self._graph.list_entities()

    def list_predicates(self) -> List[str]:
        """Return all predicate types in the knowledge graph."""
        return self._graph.list_predicates()

    # ------------------------------------------------------------------
    # RAG
    # ------------------------------------------------------------------

    @property
    def rag(self) -> RAGEngine:
        """A :class:`~context_lite_db.rag.RAGEngine` bound to this database."""
        if self._rag_engine is None:
            self._rag_engine = RAGEngine(self)
        return self._rag_engine
