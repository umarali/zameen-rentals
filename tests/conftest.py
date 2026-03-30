"""Shared pytest fixtures for ZameenRentals test suite."""
import os, sqlite3, tempfile
import pytest

# Force a test database so we don't pollute production data
_test_db_dir = tempfile.mkdtemp()
os.environ.setdefault("ZAMEENRENTALS_DB_DIR", _test_db_dir)

# Patch the database module to use the test directory BEFORE any app imports
import app.database as db_mod
db_mod._DB_DIR = type(db_mod._DB_DIR)(_test_db_dir)
db_mod._DB_PATH = db_mod._DB_DIR / "test_zameenrentals.db"
db_mod._conn = None  # Reset connection


@pytest.fixture(autouse=True)
def fresh_db():
    """Reset the database for each test."""
    db_mod._conn = None
    if db_mod._DB_PATH.exists():
        db_mod._DB_PATH.unlink()
    db_mod.init_db()
    yield
    db_mod.close_db()
    if db_mod._DB_PATH.exists():
        db_mod._DB_PATH.unlink()


@pytest.fixture
def db_conn(fresh_db):
    """Return a live database connection."""
    return db_mod._get_conn()
