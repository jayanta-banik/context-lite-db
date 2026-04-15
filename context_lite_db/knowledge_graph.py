"""
context_lite_db – knowledge graph module.

Implements a simple triple-store (subject / predicate / object) backed by
SQLite.  Edges can carry arbitrary JSON metadata and an optional weight.

Schema (table ``cldb_triples``)
--------------------------------
id          INTEGER PRIMARY KEY AUTOINCREMENT
subject     TEXT NOT NULL
predicate   TEXT NOT NULL
object      TEXT NOT NULL
weight      REAL NOT NULL DEFAULT 1.0
metadata    TEXT               – JSON-encoded arbitrary metadata
created_at  REAL               – unix timestamp

Uniqueness constraint on (subject, predicate, object).
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Tuple


class KnowledgeGraph:
    """Triple-store knowledge graph backed by SQLite.

    Parameters
    ----------
    conn:
        An open ``sqlite3.Connection`` (shared with the main DB).
    """

    TABLE = "cldb_triples"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT    NOT NULL,
                predicate   TEXT    NOT NULL,
                object      TEXT    NOT NULL,
                weight      REAL    NOT NULL DEFAULT 1.0,
                metadata    TEXT,
                created_at  REAL    NOT NULL,
                UNIQUE(subject, predicate, object)
            )
            """
        )
        self._conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_cldb_triples_subject "
            f"ON {self.TABLE}(subject)"
        )
        self._conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_cldb_triples_object "
            f"ON {self.TABLE}(object)"
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_triple(
        self,
        subject: str,
        predicate: str,
        obj: str,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Insert or replace a (subject, predicate, object) triple.

        Returns the row *id*.
        """
        meta_json = json.dumps(metadata) if metadata is not None else None
        cur = self._conn.execute(
            f"""
            INSERT INTO {self.TABLE}
                (subject, predicate, object, weight, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(subject, predicate, object)
            DO UPDATE SET
                weight     = excluded.weight,
                metadata   = excluded.metadata,
                created_at = excluded.created_at
            """,
            (subject, predicate, obj, weight, meta_json, time.time()),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def remove_triple(self, subject: str, predicate: str, obj: str) -> bool:
        """Delete a specific triple.  Returns ``True`` if it existed."""
        cur = self._conn.execute(
            f"DELETE FROM {self.TABLE} WHERE subject = ? AND predicate = ? AND object = ?",
            (subject, predicate, obj),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def remove_entity(self, entity: str) -> int:
        """Delete every triple where *entity* appears as subject or object."""
        cur = self._conn.execute(
            f"DELETE FROM {self.TABLE} WHERE subject = ? OR object = ?",
            (entity, entity),
        )
        self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Read / Query
    # ------------------------------------------------------------------

    def query(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Flexible triple pattern match.

        Pass ``None`` to act as a wildcard.  E.g.
        ``query(subject="Alice")`` returns all triples where Alice is the
        subject; ``query(predicate="knows")`` returns all "knows" edges.
        """
        filters: List[str] = []
        params: List[str] = []
        if subject is not None:
            filters.append("subject = ?")
            params.append(subject)
        if predicate is not None:
            filters.append("predicate = ?")
            params.append(predicate)
        if obj is not None:
            filters.append("object = ?")
            params.append(obj)

        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        rows = self._conn.execute(
            f"SELECT id, subject, predicate, object, weight, metadata, created_at "
            f"FROM {self.TABLE} {where}",
            params,
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def neighbors(
        self,
        entity: str,
        predicate: Optional[str] = None,
        direction: str = "out",
    ) -> List[str]:
        """Return the direct neighbours of *entity*.

        Parameters
        ----------
        entity:
            The entity whose neighbours to find.
        predicate:
            Restrict to a specific predicate.  ``None`` matches all.
        direction:
            ``"out"`` – follow edges where *entity* is the subject;
            ``"in"``  – follow edges where *entity* is the object;
            ``"both"`` – both directions.
        """
        result: Set[str] = set()

        if direction in ("out", "both"):
            rows = self.query(subject=entity, predicate=predicate)
            result.update(r["object"] for r in rows)

        if direction in ("in", "both"):
            rows = self.query(obj=entity, predicate=predicate)
            result.update(r["subject"] for r in rows)

        return sorted(result)

    def traverse(
        self,
        start: str,
        predicate: Optional[str] = None,
        direction: str = "out",
        max_depth: int = 3,
    ) -> Dict[str, List[str]]:
        """BFS traversal from *start* up to *max_depth* hops.

        Returns a dict mapping each visited entity to the list of entities
        it connects to (in the chosen direction).
        """
        visited: Dict[str, List[str]] = {}
        queue = [(start, 0)]
        seen: Set[str] = {start}

        while queue:
            entity, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            nbrs = self.neighbors(entity, predicate=predicate, direction=direction)
            visited[entity] = nbrs
            for nbr in nbrs:
                if nbr not in seen:
                    seen.add(nbr)
                    queue.append((nbr, depth + 1))

        return visited

    def get_entity_triples(self, entity: str) -> List[Dict[str, Any]]:
        """Return all triples where *entity* appears as subject or object."""
        rows = self._conn.execute(
            f"SELECT id, subject, predicate, object, weight, metadata, created_at "
            f"FROM {self.TABLE} WHERE subject = ? OR object = ?",
            (entity, entity),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_entities(self) -> List[str]:
        """Return a deduplicated sorted list of all entities in the graph."""
        subj = {r[0] for r in self._conn.execute(f"SELECT DISTINCT subject FROM {self.TABLE}").fetchall()}
        objs = {r[0] for r in self._conn.execute(f"SELECT DISTINCT object  FROM {self.TABLE}").fetchall()}
        return sorted(subj | objs)

    def list_predicates(self) -> List[str]:
        """Return a deduplicated sorted list of all predicate types."""
        rows = self._conn.execute(
            f"SELECT DISTINCT predicate FROM {self.TABLE} ORDER BY predicate"
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _row_to_dict(self, row: Tuple) -> Dict[str, Any]:
        return {
            "id": row[0],
            "subject": row[1],
            "predicate": row[2],
            "object": row[3],
            "weight": row[4],
            "metadata": json.loads(row[5]) if row[5] else None,
            "created_at": row[6],
        }
