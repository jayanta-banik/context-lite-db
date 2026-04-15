"""Tests for the file-backed native ContextDB backend and schema support."""

from __future__ import annotations

import json
import subprocess

from context_lite_db import ContextDB
from context_lite_db.native import ensure_contextdb_binary


def test_apply_schema_and_crud_with_native_backend(tmp_path):
    schema_path = tmp_path / "context.schema"
    db_path = tmp_path / "context.db"
    schema_path.write_text(
        """
model users {
  id Int @id
  name String
  score Int @default(0)
  active Boolean @default(true)

  @@index([name], name: \"idx_users_name\")
}
""".strip()
    )

    db = ContextDB(
        str(db_path),
        embedding_provider="callable",
        embedding_fn=lambda text: [float(len(text))],
        relational_backend="native",
    )
    try:
        result = db.apply_schema(str(schema_path))
        assert result["models"] == ["users"]

        row_id = db.users.create({"name": "Alice", "score": 7, "active": True})
        assert row_id == 1

        rows = db.users.find_many("name = ?", ["Alice"])
        assert rows == [
            {"id": 1, "name": "Alice", "score": 7, "active": 1},
        ]

        updated = db.users.update({"score": 9}, "name = ?", ["Alice"])
        assert updated == 1
        assert db.users.find_first("name = ?", ["Alice"])["score"] == 9

        inspection = db.inspect()
        assert any(table["name"] == "users" for table in inspection["tables"])
    finally:
        db.close()


def test_contextdb_cli_inspect_and_query(tmp_path):
    binary = ensure_contextdb_binary()
    db_path = tmp_path / "cli.db"

    subprocess.run(
        [
            binary,
            "query",
            "--db",
            str(db_path),
            "--sql",
            "CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            binary,
            "insert",
            "--db",
            str(db_path),
            "--table",
            "notes",
            "--data",
            json.dumps({"title": "hello"}),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    inspect_result = subprocess.run(
        [binary, "inspect", "--db", str(db_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    query_result = subprocess.run(
        [binary, "query", "--db", str(db_path), "--sql", "SELECT title FROM notes"],
        check=True,
        capture_output=True,
        text=True,
    )

    inspected = json.loads(inspect_result.stdout)
    queried = json.loads(query_result.stdout)
    assert inspected["tables"][0]["name"] == "notes"
    assert queried == [{"title": "hello"}]
