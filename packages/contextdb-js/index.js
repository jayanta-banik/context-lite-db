const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

class ContextDB {
  constructor(dbPath, options = {}) {
    if (!dbPath) {
      throw new Error("dbPath is required");
    }
    this.dbPath = dbPath;
    this.binaryPath = options.binaryPath || resolveBinaryPath();
  }

  query(sql, params = []) {
    return this.#rpc("query", { sql, params });
  }

  execute(sql, params = []) {
    return this.#rpc("execute", { sql, params });
  }

  createTable(table, columns, ifNotExists = true) {
    return this.#rpc("create_table", { table, columns, if_not_exists: ifNotExists });
  }

  insert(table, data) {
    return this.#rpc("insert", { table, data }).row_id;
  }

  update(table, data, where, params = []) {
    return this.#rpc("update", { table, data, where, params }).rows_affected;
  }

  delete(table, where, params = []) {
    return this.#rpc("delete", { table, where, params }).rows_affected;
  }

  applySchema(schemaPath = path.resolve(process.cwd(), "context.schema")) {
    return this.#rpc("apply_schema", { schema_path: schemaPath });
  }

  inspect() {
    return this.#rpc("inspect", {});
  }

  #rpc(action, params) {
    const payload = JSON.stringify({ action, params });
    const result = spawnSync(this.binaryPath, ["rpc", "--db", this.dbPath], {
      input: payload,
      encoding: "utf8",
    });

    const stdout = (result.stdout || "").trim();
    const stderr = (result.stderr || "").trim();
    let response = null;
    if (stdout) {
      response = JSON.parse(stdout);
    }

    if (result.status !== 0) {
      const message = response && response.error ? response.error : stderr || "ContextDB RPC failed";
      throw new Error(message);
    }

    if (!response || !response.ok) {
      throw new Error(stdout || stderr || "Invalid ContextDB response");
    }

    return response.result;
  }
}

function resolveBinaryPath() {
  const envBinary = process.env.CONTEXTDB_BINARY;
  const candidates = [
    envBinary,
    path.join(__dirname, "bin", process.platform === "win32" ? "contextdb.exe" : "contextdb"),
    path.resolve(__dirname, "..", "..", "target", "release", process.platform === "win32" ? "contextdb.exe" : "contextdb"),
    path.resolve(__dirname, "..", "..", "target", "debug", process.platform === "win32" ? "contextdb.exe" : "contextdb"),
    path.resolve(__dirname, "..", "..", "crates", "contextdb", "target", "release", process.platform === "win32" ? "contextdb.exe" : "contextdb"),
    path.resolve(__dirname, "..", "..", "crates", "contextdb", "target", "debug", process.platform === "win32" ? "contextdb.exe" : "contextdb"),
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  throw new Error("Could not locate the standalone contextdb binary");
}

module.exports = { ContextDB, resolveBinaryPath };
