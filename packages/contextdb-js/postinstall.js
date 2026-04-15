const { copyFileSync, existsSync, mkdirSync } = require("node:fs");
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..", "..");
const binaryName = process.platform === "win32" ? "contextdb.exe" : "contextdb";
const bundledBinary = path.join(__dirname, "bin", binaryName);
const releaseBinary = path.join(repoRoot, "target", "release", binaryName);
const manifestPath = path.join(repoRoot, "crates", "contextdb", "Cargo.toml");

if (!existsSync(releaseBinary)) {
  const cargo = spawnSync(
    "cargo",
    ["build", "--manifest-path", manifestPath, "--release", "--target-dir", path.join(repoRoot, "target")],
    {
      cwd: repoRoot,
      stdio: "inherit",
    },
  );
  if (cargo.status !== 0) {
    process.exit(cargo.status || 1);
  }
}

mkdirSync(path.dirname(bundledBinary), { recursive: true });
copyFileSync(releaseBinary, bundledBinary);
