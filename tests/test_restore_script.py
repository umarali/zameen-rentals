"""deploy/backup/zameenrentals-restore.sh, run for real against temp files.

systemctl is replaced by a stub that records each call, so the tests check the
order the script stops and starts things, not just its final state.
"""
import gzip
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "backup" / "zameenrentals-restore.sh"

pytestmark = pytest.mark.skipif(shutil.which("sqlite3") is None, reason="needs the sqlite3 CLI")


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE listings (id INTEGER PRIMARY KEY, title TEXT)")
    conn.executemany("INSERT INTO listings (title) VALUES (?)", [(f"listing {i}",) for i in range(rows)])
    conn.commit()
    conn.close()


@pytest.fixture
def env(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    calls = tmp_path / "systemctl.log"
    stub = tmp_path / "systemctl"
    stub.write_text(f'#!/bin/bash\necho "$*" >> "{calls}"\nexit 0\n')
    stub.chmod(0o755)
    return {
        "data": data,
        "calls": calls,
        "vars": {**os.environ, "ZR_DATA_DIR": str(data), "ZR_SYSTEMCTL": str(stub),
                 "ZR_RESTORE_ALLOW_NONROOT": "1", "ZR_WAIT_SECONDS": "3"},
    }


def _run(env, snapshot):
    return subprocess.run(["bash", str(SCRIPT), str(snapshot)], env=env["vars"],
                          capture_output=True, text=True, timeout=60)


def _calls(env):
    return env["calls"].read_text().splitlines() if env["calls"].exists() else []


def _count(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    finally:
        conn.close()


def test_restore_stops_everything_first_and_keeps_old_wal_files_together(env, tmp_path):
    db = env["data"] / "zameenrentals.db"
    _make_db(db, 2)
    (env["data"] / "zameenrentals.db-wal").write_text("old wal")
    (env["data"] / "zameenrentals.db-shm").write_text("old shm")
    snapshot = tmp_path / "snap.db"
    _make_db(snapshot, 5)

    result = _run(env, snapshot)

    assert result.returncode == 0, result.stderr
    assert _calls(env) == [
        "stop zameenrentals-backup.timer",
        "stop zameenrentals-backup.service",
        "stop zameenrentals-crawler",
        "stop zameenrentals-web",
        "start zameenrentals-web",
        "start zameenrentals-crawler",
        "start zameenrentals-backup.timer",
        "is-active --quiet zameenrentals-web",
        "is-active --quiet zameenrentals-crawler",
        "is-active --quiet zameenrentals-backup.timer",
    ]
    assert _count(db) == 5
    # No stale WAL files beside the restored database.
    assert not (env["data"] / "zameenrentals.db-wal").exists()
    assert not (env["data"] / "zameenrentals.db-shm").exists()
    kept = list(env["data"].glob("pre-restore-*"))
    assert len(kept) == 1
    assert sorted(p.name for p in kept[0].iterdir()) == [
        "zameenrentals.db", "zameenrentals.db-shm", "zameenrentals.db-wal",
    ]
    assert _count(kept[0] / "zameenrentals.db") == 2


def test_bad_snapshot_is_rejected_before_any_service_stops(env, tmp_path):
    db = env["data"] / "zameenrentals.db"
    _make_db(db, 2)
    bad = tmp_path / "bad.db"
    bad.write_text("not a database")

    result = _run(env, bad)

    assert result.returncode != 0
    assert _calls(env) == []
    assert _count(db) == 2
    assert not list(env["data"].glob("pre-restore-*"))


@pytest.mark.skipif(shutil.which("lsof") is None, reason="needs lsof")
def test_open_database_is_never_replaced(env, tmp_path):
    db = env["data"] / "zameenrentals.db"
    _make_db(db, 2)
    snapshot = tmp_path / "snap.db"
    _make_db(snapshot, 5)
    holder = sqlite3.connect(db)  # stands in for a service that didn't stop
    holder.execute("SELECT COUNT(*) FROM listings").fetchone()
    try:
        result = _run(env, snapshot)
    finally:
        holder.close()

    assert result.returncode != 0
    assert "still open" in result.stderr
    assert _count(db) == 2
    assert not list(env["data"].glob("pre-restore-*"))
    assert not any(c.startswith("start") for c in _calls(env))


def test_empty_snapshot_is_rejected(env, tmp_path):
    empty = tmp_path / "empty.db"
    _make_db(empty, 0)

    result = _run(env, empty)

    assert result.returncode != 0
    assert "No listings" in result.stderr
    assert _calls(env) == []


def test_gzipped_snapshot_seeds_a_fresh_server(env, tmp_path):
    raw = tmp_path / "snap.db"
    _make_db(raw, 3)
    gz = tmp_path / "zameenrentals-2026-10-07.db.gz"
    gz.write_bytes(gzip.compress(raw.read_bytes()))

    result = _run(env, gz)

    assert result.returncode == 0, result.stderr
    assert _count(env["data"] / "zameenrentals.db") == 3
    assert not list(env["data"].glob("pre-restore-*"))
    assert "fresh install" in result.stdout


def test_deploy_starts_backup_timer_after_code_and_checks_next_run():
    deploy = (ROOT / "deploy" / "deploy.sh").read_text()
    pip = deploy.index("pip install")
    start = deploy.index("systemctl enable --now zameenrentals-backup.timer")
    assert pip < start
    assert "NextElapseUSecRealtime" in deploy[start:]
    assert "is-active --quiet zameenrentals-backup.timer" in deploy[start:]


def test_docs_use_the_restore_tool_not_a_raw_copy():
    for doc in (ROOT / "deploy" / "backup" / "README.md", ROOT / "docs" / "digitalocean-deployment.md"):
        text = doc.read_text()
        assert "zameenrentals-restore" in text, doc
        assert "cp /tmp/zameenrentals" not in text, doc
        assert "install -o zrentals" not in text, doc
