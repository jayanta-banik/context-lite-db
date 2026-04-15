"""
context_lite_db – seed file loader.

:func:`load_seed` parses a JSON (or YAML, if PyYAML is installed) seed file
and applies it to a :class:`~context_lite_db.db.ContextDB` instance.

Seed file format (JSON)
-----------------------

.. code-block:: json

    {
      "tables": {
        "users": {
          "columns": {"name": "TEXT", "email": "TEXT"},
          "rows": [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob",   "email": "bob@example.com"}
          ]
        },
        "posts": {
          "columns": {"title": "TEXT", "body": "TEXT"},
          "rows": [
            {"title": "Hello", "body": "World"}
          ]
        }
      },
      "triples": [
        {"subject": "Alice", "predicate": "wrote", "object": "Hello",
         "weight": 1.0, "metadata": {"year": 2024}}
      ]
    }

All top-level keys are optional:

``tables``
    Dict of ``table_name → table_def``.  Each table definition may contain:

    * ``columns`` (required) – mapping of ``column_name → SQLite type``.
    * ``rows`` (optional) – list of row dicts to insert after table creation.
    * ``if_not_exists`` (optional, default ``true``) – passed to
      :meth:`~context_lite_db.db.ContextDB.create_table`.

``triples``
    List of knowledge-graph triples.  Each item must have ``subject``,
    ``predicate``, and ``object`` keys.  ``weight`` (float, default ``1.0``)
    and ``metadata`` (dict, default ``None``) are optional.

``documents``
    List of documents to embed and store in the vector store.  Each item
    must have ``doc_id`` and ``text`` keys.  ``collection`` (default
    ``"default"``), ``metadata`` (dict, default ``None``) are optional.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from .db import ContextDB


def _load_file(path: str) -> Dict[str, Any]:
    """Load a seed file from *path*.

    Supports ``.json`` natively; ``.yaml`` / ``.yml`` if PyYAML is installed.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required to load YAML seed files. "
                "Install it with: pip install pyyaml"
            ) from exc
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    else:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)


class SeedResult:
    """Summary of what was created/inserted by :func:`load_seed`.

    Attributes
    ----------
    tables_created : list[str]
        Names of tables that were created.
    rows_inserted : dict[str, int]
        Mapping of ``table_name → number of rows inserted``.
    triples_added : int
        Number of knowledge-graph triples added.
    documents_added : int
        Number of documents added to the vector store.
    """

    def __init__(self) -> None:
        self.tables_created: list[str] = []
        self.rows_inserted: Dict[str, int] = {}
        self.triples_added: int = 0
        self.documents_added: int = 0

    def __repr__(self) -> str:
        return (
            f"SeedResult(tables_created={self.tables_created!r}, "
            f"rows_inserted={self.rows_inserted!r}, "
            f"triples_added={self.triples_added!r}, "
            f"documents_added={self.documents_added!r})"
        )


def load_seed(db: "ContextDB", path: str) -> SeedResult:
    """Parse *path* and apply its seed definitions to *db*.

    Parameters
    ----------
    db:
        The :class:`~context_lite_db.db.ContextDB` instance to seed.
    path:
        Absolute or relative path to the seed file (``.json``, ``.yaml``,
        or ``.yml``).

    Returns
    -------
    SeedResult
        A summary object describing what was created and inserted.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the seed file is missing required fields.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Seed file not found: {path}")

    data = _load_file(path)
    result = SeedResult()

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------
    for table_name, table_def in data.get("tables", {}).items():
        if "columns" not in table_def:
            raise ValueError(
                f"Seed file: table '{table_name}' is missing the 'columns' key"
            )
        columns = table_def["columns"]
        if not isinstance(columns, dict):
            raise ValueError(
                f"Seed file: 'columns' for table '{table_name}' must be a dict"
            )
        if_not_exists = table_def.get("if_not_exists", True)
        db.create_table(table_name, columns, if_not_exists=if_not_exists)
        result.tables_created.append(table_name)

        rows = table_def.get("rows", [])
        if rows:
            ids = db.seed_table(table_name, rows)
            result.rows_inserted[table_name] = len(ids)

    # ------------------------------------------------------------------
    # Knowledge-graph triples
    # ------------------------------------------------------------------
    for triple in data.get("triples", []):
        for key in ("subject", "predicate", "object"):
            if key not in triple:
                raise ValueError(
                    f"Seed file: triple is missing required key '{key}': {triple!r}"
                )
        db.add_triple(
            subject=triple["subject"],
            predicate=triple["predicate"],
            obj=triple["object"],
            weight=float(triple.get("weight", 1.0)),
            metadata=triple.get("metadata"),
        )
        result.triples_added += 1

    # ------------------------------------------------------------------
    # Vector-store documents
    # ------------------------------------------------------------------
    for doc in data.get("documents", []):
        for key in ("doc_id", "text"):
            if key not in doc:
                raise ValueError(
                    f"Seed file: document is missing required key '{key}': {doc!r}"
                )
        db.add_document(
            doc_id=doc["doc_id"],
            text=doc["text"],
            collection=doc.get("collection", "default"),
            metadata=doc.get("metadata"),
        )
        result.documents_added += 1

    return result
