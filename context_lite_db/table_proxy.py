"""
context_lite_db – table proxy module.

Provides :class:`TableProxy`, a thin wrapper around a specific table that
exposes a Prisma-style CRUD API::

    db = ContextDB("mydb.db")
    db.create_table("users", {"name": "TEXT", "email": "TEXT"})

    # Prisma-style access via attribute
    db.users.create({"name": "Alice", "email": "alice@example.com"})
    db.users.find_all()
    db.users.update({"name": "Dr. Alice"}, where="email = ?", params=["alice@example.com"])
    db.users.delete(where="name = ?", params=["Dr. Alice"])
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union


class TableProxy:
    """Prisma-style table accessor."""

    def __init__(self, db: Any, table: str) -> None:
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "_table", table)

    def create(self, data: Dict[str, Any]) -> int:
        """Insert a single row and return its *id*."""
        return self._db.insert(self._table, data)

    def create_many(self, rows: List[Dict[str, Any]]) -> List[int]:
        """Insert multiple rows in a single transaction."""
        return self._db.batch_insert(self._table, rows)

    def seed_table(self, rows: List[Dict[str, Any]]) -> List[int]:
        """Bulk-insert initial data (alias for :meth:`create_many`)."""
        return self.create_many(rows)

    def find_all(self) -> List[Dict[str, Any]]:
        """Return every row in the table."""
        return self._db.query(f"SELECT * FROM {self._table}")

    def find_many(
        self,
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> List[Dict[str, Any]]:
        """Return all rows matching *where*."""
        return self._db.query(f"SELECT * FROM {self._table} WHERE {where}", params)

    def find_first(
        self,
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the first row matching *where*, or ``None``."""
        rows = self._db.query(f"SELECT * FROM {self._table} WHERE {where} LIMIT 1", params)
        return rows[0] if rows else None

    def update(
        self,
        data: Dict[str, Any],
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> int:
        """Update all rows matching *where* with values in *data*."""
        return self._db.update(self._table, data, where, params)

    def update_many(self, updates: List[Dict[str, Any]]) -> int:
        """Apply multiple update operations in a single transaction."""
        return self._db.batch_update(self._table, updates)

    def delete(
        self,
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> int:
        """Delete all rows matching *where*."""
        return self._db.delete(self._table, where, params)

    def delete_many(self, conditions: List[Dict[str, Any]]) -> int:
        """Apply multiple delete operations in a single transaction."""
        return self._db.batch_delete(self._table, conditions)

    def drop(self) -> None:
        """Drop this table from the database (irreversible)."""
        self._db.drop_table(self._table)

    def truncate(self) -> None:
        """Delete every row in this table without dropping the schema."""
        self._db.truncate_table(self._table)

    def __repr__(self) -> str:
        return f"TableProxy(table={self._table!r})"
