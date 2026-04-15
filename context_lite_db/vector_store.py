"""
context_lite_db – vector store module.

Stores document embeddings as BLOBs inside SQLite and provides
cosine-similarity based nearest-neighbour retrieval.

Schema (table ``cldb_vectors``)
--------------------------------
id          INTEGER PRIMARY KEY AUTOINCREMENT
doc_id      TEXT NOT NULL          – application-level document identifier
collection  TEXT NOT NULL DEFAULT 'default'
text        TEXT NOT NULL          – original text chunk
embedding   BLOB NOT NULL          – numpy float32 vector serialised with
                                     numpy.save / numpy.load
metadata    TEXT                   – JSON-encoded arbitrary metadata
created_at  REAL                   – unix timestamp
"""

from __future__ import annotations

import json
import sqlite3
import time
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vec_to_blob(vector: List[float]) -> bytes:
    arr = np.array(vector, dtype=np.float32)
    buf = BytesIO()
    np.save(buf, arr)
    return buf.getvalue()


def _blob_to_vec(blob: bytes) -> np.ndarray:
    buf = BytesIO(blob)
    return np.load(buf)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class VectorStore:
    """Manages the ``cldb_vectors`` table and nearest-neighbour search.

    Parameters
    ----------
    conn:
        An open ``sqlite3.Connection`` (shared with the main DB).
    """

    TABLE = "cldb_vectors"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id      TEXT    NOT NULL,
                collection  TEXT    NOT NULL DEFAULT 'default',
                text        TEXT    NOT NULL,
                embedding   BLOB    NOT NULL,
                metadata    TEXT,
                created_at  REAL    NOT NULL
            )
            """
        )
        self._conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_cldb_vectors_collection "
            f"ON {self.TABLE}(collection)"
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(
        self,
        doc_id: str,
        text: str,
        embedding: List[float],
        collection: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Insert a document chunk and its embedding.

        Returns the auto-assigned row *id*.
        """
        blob = _vec_to_blob(embedding)
        meta_json = json.dumps(metadata) if metadata is not None else None
        cur = self._conn.execute(
            f"""
            INSERT INTO {self.TABLE}
                (doc_id, collection, text, embedding, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doc_id, collection, text, blob, meta_json, time.time()),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def delete(self, doc_id: str, collection: str = "default") -> int:
        """Delete all rows with the given *doc_id* in *collection*.

        Returns the number of rows deleted.
        """
        cur = self._conn.execute(
            f"DELETE FROM {self.TABLE} WHERE doc_id = ? AND collection = ?",
            (doc_id, collection),
        )
        self._conn.commit()
        return cur.rowcount

    def delete_collection(self, collection: str) -> int:
        """Delete every document in *collection*."""
        cur = self._conn.execute(
            f"DELETE FROM {self.TABLE} WHERE collection = ?",
            (collection,),
        )
        self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, doc_id: str, collection: str = "default") -> List[Dict[str, Any]]:
        """Retrieve all rows for *doc_id* in *collection*."""
        rows = self._conn.execute(
            f"SELECT id, doc_id, collection, text, embedding, metadata, created_at "
            f"FROM {self.TABLE} WHERE doc_id = ? AND collection = ?",
            (doc_id, collection),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_collections(self) -> List[str]:
        """Return the distinct collection names stored in the vector table."""
        rows = self._conn.execute(
            f"SELECT DISTINCT collection FROM {self.TABLE} ORDER BY collection"
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Semantic search
    # ------------------------------------------------------------------

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        collection: Optional[str] = None,
        threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Return the *top_k* most similar documents to *query_embedding*.

        Parameters
        ----------
        query_embedding:
            Dense vector of the same dimensionality as stored embeddings.
        top_k:
            Maximum number of results to return.
        collection:
            Restrict search to this collection.  ``None`` searches all.
        threshold:
            Minimum cosine-similarity score; results below are excluded.
        """
        query_vec = np.array(query_embedding, dtype=np.float32)

        if collection is not None:
            rows = self._conn.execute(
                f"SELECT id, doc_id, collection, text, embedding, metadata, created_at "
                f"FROM {self.TABLE} WHERE collection = ?",
                (collection,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT id, doc_id, collection, text, embedding, metadata, created_at "
                f"FROM {self.TABLE}"
            ).fetchall()

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for row in rows:
            vec = _blob_to_vec(row[4])
            score = _cosine_similarity(query_vec, vec)
            if score >= threshold:
                d = self._row_to_dict(row)
                d["score"] = score
                scored.append((score, d))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _row_to_dict(self, row: Tuple) -> Dict[str, Any]:
        return {
            "id": row[0],
            "doc_id": row[1],
            "collection": row[2],
            "text": row[3],
            "embedding": _blob_to_vec(row[4]).tolist(),
            "metadata": json.loads(row[5]) if row[5] else None,
            "created_at": row[6],
        }
