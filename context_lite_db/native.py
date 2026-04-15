"""Helpers for running the standalone Rust ``contextdb`` binary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


class NativeContextDBError(RuntimeError):
    """Raised when the standalone ContextDB binary fails."""


class NativeContextDBClient:
    """Subprocess-backed client for the Rust ``contextdb`` binary."""

    def __init__(self, db_path: str, binary_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self.binary_path = binary_path or ensure_contextdb_binary()

    def execute(self, sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        return self._rpc("execute", {"sql": sql, "params": list(params or [])})

    def query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        result = self._rpc("query", {"sql": sql, "params": list(params or [])})
        if not isinstance(result, list):
            raise NativeContextDBError(f"Unexpected query response: {result!r}")
        return result

    def create_table(
        self,
        table: str,
        columns: Dict[str, str],
        if_not_exists: bool = True,
    ) -> None:
        self._rpc(
            "create_table",
            {
                "table": table,
                "columns": columns,
                "if_not_exists": if_not_exists,
            },
        )

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        result = self._rpc("insert", {"table": table, "data": data})
        return int(result["row_id"])

    def batch_insert(self, table: str, rows: List[Dict[str, Any]]) -> List[int]:
        result = self._rpc("batch_insert", {"table": table, "rows": rows})
        if not isinstance(result, list):
            raise NativeContextDBError(f"Unexpected batch insert response: {result!r}")
        return [int(item) for item in result]

    def update(
        self,
        table: str,
        data: Dict[str, Any],
        where: str,
        params: Optional[List[Any]] = None,
    ) -> int:
        result = self._rpc(
            "update",
            {
                "table": table,
                "data": data,
                "where": where,
                "params": list(params or []),
            },
        )
        return int(result["rows_affected"])

    def batch_update(self, table: str, updates: List[Dict[str, Any]]) -> int:
        result = self._rpc("batch_update", {"table": table, "updates": updates})
        return int(result["rows_affected"])

    def delete(
        self,
        table: str,
        where: str,
        params: Optional[List[Any]] = None,
    ) -> int:
        result = self._rpc(
            "delete",
            {
                "table": table,
                "where": where,
                "params": list(params or []),
            },
        )
        return int(result["rows_affected"])

    def batch_delete(self, table: str, conditions: List[Dict[str, Any]]) -> int:
        result = self._rpc("batch_delete", {"table": table, "conditions": conditions})
        return int(result["rows_affected"])

    def drop_table(self, table: str) -> None:
        self._rpc("drop_table", {"table": table})

    def truncate_table(self, table: str) -> None:
        self._rpc("truncate_table", {"table": table})

    def apply_schema(self, schema_path: str) -> Dict[str, Any]:
        result = self._rpc("apply_schema", {"schema_path": schema_path})
        if not isinstance(result, dict):
            raise NativeContextDBError(f"Unexpected schema response: {result!r}")
        return result

    def inspect(self) -> Dict[str, Any]:
        result = self._rpc("inspect", {})
        if not isinstance(result, dict):
            raise NativeContextDBError(f"Unexpected inspect response: {result!r}")
        return result

    def _rpc(self, action: str, params: Dict[str, Any]) -> Any:
        payload = json.dumps({"action": action, "params": params})
        proc = subprocess.run(
            [self.binary_path, "rpc", "--db", self.db_path],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        response = None
        if stdout:
            try:
                response = json.loads(stdout)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive path
                raise NativeContextDBError(
                    f"Failed to decode ContextDB output: {stdout}\n{stderr}"
                ) from exc

        if proc.returncode != 0:
            message = stderr or "ContextDB binary failed"
            if isinstance(response, dict) and response.get("error"):
                message = str(response["error"])
            raise NativeContextDBError(message)

        if not isinstance(response, dict) or not response.get("ok"):
            raise NativeContextDBError(
                f"Unexpected ContextDB RPC response: {stdout or stderr}"
            )
        return response.get("result")


def ensure_contextdb_binary() -> str:
    for candidate in _candidate_binary_paths():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    cargo = shutil.which("cargo")
    manifest_path = _project_root() / "crates" / "contextdb" / "Cargo.toml"
    if not cargo or not manifest_path.exists():
        raise NativeContextDBError(
            "Could not find the standalone 'contextdb' binary. "
            "Set CONTEXTDB_BINARY or install/build the Rust core first."
        )

    subprocess.run(
        [
            cargo,
            "build",
            "--manifest-path",
            str(manifest_path),
            "--release",
            "--target-dir",
            str(_project_root() / "target"),
        ],
        cwd=_project_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    built_binary = _project_root() / "target" / "release" / _binary_name()
    if built_binary.is_file() and os.access(built_binary, os.X_OK):
        return str(built_binary)

    raise NativeContextDBError("Cargo build completed but the 'contextdb' binary was not found")


def _candidate_binary_paths() -> List[Path]:
    package_root = Path(__file__).resolve().parent
    project_root = _project_root()
    env_binary = os.environ.get("CONTEXTDB_BINARY")
    candidates = [
        Path(env_binary) if env_binary else None,
        package_root / "bin" / _binary_name(),
        project_root / "target" / "release" / _binary_name(),
        project_root / "target" / "debug" / _binary_name(),
        project_root / "crates" / "contextdb" / "target" / "release" / _binary_name(),
        project_root / "crates" / "contextdb" / "target" / "debug" / _binary_name(),
    ]
    return [candidate for candidate in candidates if candidate is not None]


def _binary_name() -> str:
    return "contextdb.exe" if os.name == "nt" else "contextdb"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]
