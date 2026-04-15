"""
context_lite_db – core database module.

:class:`ContextDB` is the single entry-point for all operations:

* **Relational** – plain SQL via ``execute`` / ``query``, plus convenience
  helpers ``create_table``, ``insert``, ``update``, ``delete``.
* **Prisma-style table access** – ``db.table_name.create(...)``,
  ``db.table_name.find_all()``, etc.
* **Schema-first workflows** – ``db.apply_schema("context.schema")`` delegates
  table creation to the standalone Rust ``contextdb`` engine.
* **Semantic search** – ``add_document`` + ``semantic_search``.
* **Knowledge graph** – ``add_triple``, ``remove_triple``, ``graph_query``,
  ``graph_traverse``.
* **RAG** – ``rag`` property returns a :class:`~context_lite_db.rag.RAGEngine`
  pre-wired to this database instance.
* **Seed from file** – ``db.seed(path)`` creates tables, inserts rows, adds
  graph triples, and embeds documents from a JSON/YAML seed file.

``ContextLiteDB`` is kept as a backwards-compatible alias.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

from .embeddings import EmbeddingProvider
from .knowledge_graph import KnowledgeGraph
from .native import NativeContextDBClient
from .rag import RAGEngine
from .seed import SeedResult, load_seed
from .table_proxy import TableProxy
from .vector_store import VectorStore


@dataclass
class ExecutionResult:
    """Minimal execute result for native-backed relational operations."""

    rowcount: int = -1


class ContextDB:
    """AI-native local database combining SQLite, semantic search, knowledge
    graphs, and RAG in a single file-based store.

    Supports Prisma-style table access via attribute lookup::

        db = ContextDB("mydb.db")
        db.create_table("users", {"name": "TEXT", "email": "TEXT"})
        db.users.create({"name": "Alice", "email": "alice@example.com"})
        db.users.find_all()

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
    relational_backend:
        ``"auto"`` uses the Rust standalone engine for file-backed databases and
        keeps pure-Python SQLite for ``":memory:"``.  Set to ``"python"`` to
        force the legacy in-process path or ``"native"`` to require the Rust
        engine.
    """

    def __init__(
        self,
        path: str = ":memory:",
        embedding_provider: str = "sentence-transformers",
        embedding_model: str = "all-MiniLM-L6-v2",
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
        relational_backend: Literal["auto", "python", "native"] = "auto",
    ) -> None:
        if relational_backend not in {"auto", "python", "native"}:
            raise ValueError(
                "relational_backend must be one of 'auto', 'python', or 'native'"
            )
        if relational_backend == "native" and path == ":memory:":
            raise ValueError("The native relational backend requires a file path")

        self._path = path
        self._relational_backend = relational_backend
        self._native_client: Optional[NativeContextDBClient] = None
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
    # Prisma-style table attribute access
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> TableProxy:
        """Return a :class:`~context_lite_db.table_proxy.TableProxy` for *name*.

        Called only when normal attribute lookup fails, so existing methods
        and properties are never shadowed.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return TableProxy(self, name)

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "ContextDB":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Relational helpers
    # ------------------------------------------------------------------

    def _uses_native_relational(self) -> bool:
        return self._path != ":memory:" and self._relational_backend in {
            "auto",
            "native",
        }

    def _native(self) -> NativeContextDBClient:
        if not self._uses_native_relational():
            raise RuntimeError("The native relational backend is not active")
        if self._native_client is None:
            self._native_client = NativeContextDBClient(self._path)
        return self._native_client

    def execute(
        self, sql: str, params: Union[List, Tuple, None] = None
    ) -> Union[sqlite3.Cursor, ExecutionResult]:
        """Execute raw SQL and return the cursor/result.

        Automatically commits for DML/DDL statements.
        """
        if self._uses_native_relational():
            result = self._native().execute(sql, list(params or []))
            return ExecutionResult(rowcount=int(result.get("rows_affected", -1)))

        cur = self._conn.execute(sql, params or [])
        if sql.strip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")
        ):
            self._conn.commit()
        return cur

    def query(
        self, sql: str, params: Union[List, Tuple, None] = None
    ) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results as a list of dicts."""
        if self._uses_native_relational():
            return self._native().query(sql, list(params or []))

        cur = self._conn.execute(sql, params or [])
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def create_table(
        self,
        table: str,
        columns: Dict[str, str],
        if_not_exists: bool = True,
    ) -> None:
        """Create a table with the specified column definitions."""
        if self._uses_native_relational():
            self._native().create_table(table, columns, if_not_exists=if_not_exists)
            return

        col_defs = ", ".join(f"{name} {dtype}" for name, dtype in columns.items())
        guard = "IF NOT EXISTS " if if_not_exists else ""
        self._conn.execute(
            f"CREATE TABLE {guard}{table} "
            f"(id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs})"
        )
        self._conn.commit()

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """Insert a row and return the new row *id*."""
        if self._uses_native_relational():
            return self._native().insert(table, data)

        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        cur = self._conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def batch_insert(self, table: str, rows: List[Dict[str, Any]]) -> List[int]:
        """Insert multiple rows in a single transaction."""
        if self._uses_native_relational():
            return self._native().batch_insert(table, rows)

        ids: List[int] = []
        for row in rows:
            ids.append(self.insert(table, row))
        return ids

    def update(
        self,
        table: str,
        data: Dict[str, Any],
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> int:
        """Update rows matching *where* with values in *data*."""
        if self._uses_native_relational():
            return self._native().update(table, data, where, list(params or []))

        set_clause = ", ".join(f"{k} = ?" for k in data.keys())
        all_params = list(data.values()) + list(params or [])
        cur = self._conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE {where}",
            all_params,
        )
        self._conn.commit()
        return cur.rowcount

    def batch_update(self, table: str, updates: List[Dict[str, Any]]) -> int:
        """Apply multiple updates in a single transaction."""
        if self._uses_native_relational():
            return self._native().batch_update(table, updates)

        total = 0
        for update in updates:
            total += self.update(
                table,
                update["data"],
                update["where"],
                update.get("params") or [],
            )
        return total

    def delete(
        self,
        table: str,
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> int:
        """Delete rows matching *where*.  Returns the number of rows deleted."""
        if self._uses_native_relational():
            return self._native().delete(table, where, list(params or []))

        cur = self._conn.execute(
            f"DELETE FROM {table} WHERE {where}",
            params or [],
        )
        self._conn.commit()
        return cur.rowcount

    def batch_delete(self, table: str, conditions: List[Dict[str, Any]]) -> int:
        """Apply multiple delete operations in a single transaction."""
        if self._uses_native_relational():
            return self._native().batch_delete(table, conditions)

        total = 0
        for condition in conditions:
            total += self.delete(
                table,
                condition["where"],
                condition.get("params") or [],
            )
        return total

    def apply_schema(self, path: str = "context.schema") -> Dict[str, Any]:
        """Apply a Prisma-inspired ``context.schema`` file to the database."""
        if self._uses_native_relational():
            return self._native().apply_schema(path)
        raise RuntimeError(
            "Schema application requires a file-backed database with the native backend"
        )

    def inspect(self) -> Dict[str, Any]:
        """Inspect the current relational schema using the standalone engine."""
        if self._uses_native_relational():
            return self._native().inspect()
        tables = self.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return {"tables": tables}

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
        """Embed *text* and store it in the vector store."""
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
        """Find the *top_k* most semantically similar documents to *query*."""
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
        """Add or update a (subject, predicate, object) triple."""
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
    # Table-level helpers (accessible on the DB instance directly)
    # ------------------------------------------------------------------

    def drop_table(self, table: str) -> None:
        """Drop *table* from the database (irreversible)."""
        if self._uses_native_relational():
            self._native().drop_table(table)
            return
        self.execute(f"DROP TABLE IF EXISTS {table}")

    def truncate_table(self, table: str) -> None:
        """Delete every row in *table* without dropping the schema."""
        if self._uses_native_relational():
            self._native().truncate_table(table)
            return
        self.execute(f"DELETE FROM {table}")

    def seed_table(
        self,
        table: str,
        rows: List[Dict[str, Any]],
    ) -> List[int]:
        """Bulk-insert *rows* into *table* as initial seed data."""
        return TableProxy(self, table).create_many(rows)

    def seed(self, path: str) -> SeedResult:
        """Seed the database from a JSON or YAML file."""
        return load_seed(self, path)

    # ------------------------------------------------------------------
    # RAG
    # ------------------------------------------------------------------

    @property
    def rag(self) -> RAGEngine:
        """A :class:`~context_lite_db.rag.RAGEngine` bound to this database."""
        if self._rag_engine is None:
            self._rag_engine = RAGEngine(self)
        return self._rag_engine


#: Backwards-compatible alias.  Prefer :class:`ContextDB`.
ContextLiteDB = ContextDB
