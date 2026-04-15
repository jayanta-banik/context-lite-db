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
    """Prisma-style table accessor.

    Instances are created automatically when you access an attribute on
    :class:`~context_lite_db.db.ContextDB` that matches a table name::

        db.users.create({"name": "Alice"})

    Parameters
    ----------
    db:
        The owning :class:`~context_lite_db.db.ContextDB` instance.
    table:
        The SQLite table name to operate on.
    """

    def __init__(self, db: Any, table: str) -> None:
        # Use object.__setattr__ to avoid triggering ContextDB.__getattr__
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "_table", table)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: Dict[str, Any]) -> int:
        """Insert a single row and return its *id*.

        Parameters
        ----------
        data:
            Column-name → value mapping for the new row.
        """
        return self._db.insert(self._table, data)

    def create_many(self, rows: List[Dict[str, Any]]) -> List[int]:
        """Insert multiple rows in a single transaction.

        Parameters
        ----------
        rows:
            List of column-name → value mappings.

        Returns
        -------
        list[int]
            The auto-assigned *id* for each inserted row, in order.
        """
        ids: List[int] = []
        conn = self._db._conn
        for row in rows:
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" * len(row))
            cur = conn.execute(
                f"INSERT INTO {self._table} ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
            if cur.lastrowid is None:
                raise RuntimeError(
                    f"INSERT into '{self._table}' did not return a row id"
                )
            ids.append(cur.lastrowid)
        conn.commit()
        return ids

    def seed_table(self, rows: List[Dict[str, Any]]) -> List[int]:
        """Bulk-insert initial data (alias for :meth:`create_many`).

        Useful for seeding a freshly created table with default records.
        """
        return self.create_many(rows)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def find_all(self) -> List[Dict[str, Any]]:
        """Return every row in the table."""
        return self._db.query(f"SELECT * FROM {self._table}")

    def find_many(
        self,
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> List[Dict[str, Any]]:
        """Return all rows matching *where*.

        Parameters
        ----------
        where:
            SQL WHERE clause fragment (e.g. ``"age > ?"``).
        params:
            Positional parameters for the WHERE clause.
        """
        return self._db.query(
            f"SELECT * FROM {self._table} WHERE {where}", params
        )

    def find_first(
        self,
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the first row matching *where*, or ``None``.

        Parameters
        ----------
        where:
            SQL WHERE clause fragment.
        params:
            Positional parameters.
        """
        rows = self._db.query(
            f"SELECT * FROM {self._table} WHERE {where} LIMIT 1", params
        )
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        data: Dict[str, Any],
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> int:
        """Update all rows matching *where* with values in *data*.

        Parameters
        ----------
        data:
            Column-name → new-value mapping.
        where:
            SQL WHERE clause fragment.
        params:
            Positional parameters for the WHERE clause.

        Returns
        -------
        int
            Number of rows affected.
        """
        return self._db.update(self._table, data, where, params)

    def update_many(
        self,
        updates: List[Dict[str, Any]],
    ) -> int:
        """Apply multiple update operations in a single transaction.

        Parameters
        ----------
        updates:
            A list of dicts, each with keys:

            * ``"data"`` – column-name → new-value mapping *(required)*
            * ``"where"`` – SQL WHERE clause fragment *(required)*
            * ``"params"`` – positional WHERE parameters *(optional)*

        Returns
        -------
        int
            Total number of rows affected across all updates.
        """
        total = 0
        conn = self._db._conn
        for u in updates:
            data = u["data"]
            where = u["where"]
            where_params = u.get("params") or []
            set_clause = ", ".join(f"{k} = ?" for k in data.keys())
            all_params = list(data.values()) + list(where_params)
            cur = conn.execute(
                f"UPDATE {self._table} SET {set_clause} WHERE {where}",
                all_params,
            )
            total += cur.rowcount
        conn.commit()
        return total

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        where: str,
        params: Union[List, Tuple, None] = None,
    ) -> int:
        """Delete all rows matching *where*.

        Parameters
        ----------
        where:
            SQL WHERE clause fragment.
        params:
            Positional parameters.

        Returns
        -------
        int
            Number of rows deleted.
        """
        return self._db.delete(self._table, where, params)

    def delete_many(
        self,
        conditions: List[Dict[str, Any]],
    ) -> int:
        """Apply multiple delete operations in a single transaction.

        Parameters
        ----------
        conditions:
            A list of dicts, each with keys:

            * ``"where"`` – SQL WHERE clause fragment *(required)*
            * ``"params"`` – positional WHERE parameters *(optional)*

        Returns
        -------
        int
            Total number of rows deleted across all conditions.
        """
        total = 0
        conn = self._db._conn
        for c in conditions:
            where = c["where"]
            where_params = c.get("params") or []
            cur = conn.execute(
                f"DELETE FROM {self._table} WHERE {where}",
                list(where_params),
            )
            total += cur.rowcount
        conn.commit()
        return total

    # ------------------------------------------------------------------
    # Table-level operations
    # ------------------------------------------------------------------

    def drop(self) -> None:
        """Drop this table from the database (irreversible)."""
        self._db.execute(f"DROP TABLE IF EXISTS {self._table}")

    def truncate(self) -> None:
        """Delete every row in this table without dropping the schema."""
        self._db.execute(f"DELETE FROM {self._table}")

    def __repr__(self) -> str:
        return f"TableProxy(table={self._table!r})"
