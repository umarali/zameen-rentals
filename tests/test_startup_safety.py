"""Startup must respect database overrides and preserve orphan recovery files."""
import os
import subprocess
import sys

import pytest


def test_database_and_push_keys_use_configured_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", (
            "from app.database import init_db, close_db; "
            "from app.personalization import ensure_vapid_keys; "
            "init_db(); ensure_vapid_keys(); close_db()"
        )],
        env={**os.environ, "ZAMEENRENTALS_DB_DIR": str(tmp_path)},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "zameenrentals.db").exists()
    assert (tmp_path / "vapid_private.pem").exists()


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
def test_missing_database_does_not_destroy_recovery_files(tmp_path, suffix):
    recovery = tmp_path / ("zameenrentals.db" + suffix)
    recovery.write_bytes(b"recovery evidence")
    result = subprocess.run(
        [sys.executable, "-c", "from app.database import init_db; init_db()"],
        env={**os.environ, "ZAMEENRENTALS_DB_DIR": str(tmp_path)},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "SQLite recovery files exist" in result.stderr
    assert recovery.read_bytes() == b"recovery evidence"
    assert not (tmp_path / "zameenrentals.db").exists()
