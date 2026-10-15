"""Smoke-test the built ONEFILE executable without launching a Windows desktop.

Checks true first-run migration and persistence on repeated runs, with a
Unicode/space-containing installation directory. Runs on GitHub's Windows VM.
"""
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def run_executable(exe):
    result = subprocess.run(
        [str(exe), "--verify-install"],
        cwd=exe.parent,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Onefile startup failed (code {result.returncode}): "
            f"{result.stderr.decode(errors='replace')[-1500:]}"
        )


def main():
    source = Path(sys.argv[1]).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Onefile EXE is missing: {source}")
    with tempfile.TemporaryDirectory(prefix="予備品管理 Onefile ") as root:
        target = Path(root) / "テスト配置"
        target.mkdir()
        exe = target / "SparePartsManagement.exe"
        shutil.copy2(source, exe)
        db = target / "data" / "inventory.sqlite3"
        assert not db.exists(), "First startup should create SQLite"
        run_executable(exe)
        if (target / "data" / ".django-secret").exists():
            raise AssertionError("Onefile unexpectedly created an external secret file")
        if not db.is_file() or db.stat().st_size == 0:
            raise AssertionError("Onefile failed to initialize external SQLite")
        with sqlite3.connect(db) as connection:
            migrations = connection.execute(
                "SELECT COUNT(*) FROM django_migrations"
            ).fetchone()[0]
            if migrations < 7:
                raise AssertionError(f"Expected initial migrations, got {migrations}")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS __onefile_persistence (value TEXT)"
            )
            connection.execute(
                "INSERT INTO __onefile_persistence (value) VALUES (?)",
                ("在庫データを維持する",),
            )
            connection.commit()
        run_executable(exe)
        with sqlite3.connect(db) as connection:
            persisted = connection.execute(
                "SELECT value FROM __onefile_persistence"
            ).fetchone()
            if persisted != ("在庫データを維持する",):
                raise AssertionError("SQLite content changed on second startup")
        unexpected = [
            path.name for path in target.iterdir()
            if path.name not in {"SparePartsManagement.exe", "data"}
        ]
        if unexpected:
            raise AssertionError(f"Support files leaked outside the EXE: {unexpected}")
        print(f"Onefile first launch, migration and existing DB persistence OK ({migrations} migrations)")


if __name__ == "__main__":
    main()
