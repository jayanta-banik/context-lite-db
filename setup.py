from __future__ import annotations

import shutil
import subprocess
import os
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPyWithRust(build_py):
    def run(self) -> None:
        super().run()
        self._build_contextdb_binary()

    def _build_contextdb_binary(self) -> None:
        root = Path(__file__).resolve().parent
        manifest_path = root / "crates" / "contextdb" / "Cargo.toml"
        cargo = shutil.which("cargo")
        if cargo is None:
            raise RuntimeError("cargo is required to build the bundled contextdb binary")

        subprocess.run(
            [
                cargo,
                "build",
                "--manifest-path",
                str(manifest_path),
                "--release",
                "--target-dir",
                str(root / "target"),
            ],
            cwd=root,
            check=True,
        )

        binary_name = "contextdb.exe" if os.name == "nt" else "contextdb"
        built_binary = root / "target" / "release" / binary_name
        if not built_binary.exists():
            raise RuntimeError(f"Built contextdb binary not found at {built_binary}")

        target_dir = Path(self.build_lib) / "context_lite_db" / "bin"
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built_binary, target_dir / binary_name)


setup(cmdclass={"build_py": BuildPyWithRust})
