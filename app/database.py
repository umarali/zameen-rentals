"""SQLite database for persistent cache and search history."""
import json, logging, os, sqlite3, threading, time
from pathlib import Path

logger = logging.getLogger("zameenrentals")

_DB_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_PATH = _DB_DIR / "zameenrentals.db"
_conn = None
_lock = threading.Lock()

CACHE_TTL = 300
MAX_CACHE = 200


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                os.makedirs(_DB_DIR, exist_ok=True)
                _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
                _conn.row_factory = sqlite3.Row
                _conn.execute("PRAGMA journal_mode=WAL")
                _conn.execute("PRAGMA busy_timeout=5000")
    return _conn


def init_db():
    conn = _get_conn()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS listing_cache (
                cache_key   TEXT PRIMARY KEY,
                data        TEXT NOT NULL,
                city        TEXT NOT NULL DEFAULT 'lahore',
                created_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cache_created ON listing_cache(created_at);

            CREATE TABLE IF NOT EXISTS search_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                city          TEXT NOT NULL DEFAULT 'lahore',
                area          TEXT,
                property_type TEXT,
                bedrooms      INTEGER,
                price_min     INTEGER,
                price_max     INTEGER,
                furnished     INTEGER,
                sort          TEXT,
                result_count  INTEGER,
                searched_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_history_searched ON search_history(searched_at);
            CREATE INDEX IF NOT EXISTS idx_history_area ON search_history(area);
        """)
        # Clean expired cache on startup
        conn.execute("DELETE FROM listing_cache WHERE created_at < ?", (time.time() - CACHE_TTL,))
    logger.info("Database initialized at %s", _DB_PATH)


def close_db():
    global _conn
    if _conn:
        _conn.close()
        _conn = None


# ── Cache operations ──

def db_cache_get(key: str):
    conn = _get_conn()
    row = conn.execute(
        "SELECT data, created_at FROM listing_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    if row is None:
        return None
    if time.time() - row["created_at"] >= CACHE_TTL:
        conn.execute("DELETE FROM listing_cache WHERE cache_key = ?", (key,))
        conn.commit()
        return None
    return json.loads(row["data"])


def db_cache_set(key: str, data, city: str = "lahore"):
    conn = _get_conn()
    with conn:
        # Enforce max entries via LRU eviction
        count = conn.execute("SELECT COUNT(*) FROM listing_cache").fetchone()[0]
        if count >= MAX_CACHE:
            excess = count - MAX_CACHE + 1
            conn.execute(
                "DELETE FROM listing_cache WHERE cache_key IN "
                "(SELECT cache_key FROM listing_cache ORDER BY created_at ASC LIMIT ?)",
                (excess,)
            )
        conn.execute(
            "INSERT OR REPLACE INTO listing_cache (cache_key, data, city, created_at) VALUES (?, ?, ?, ?)",
            (key, json.dumps(data, default=str), city, time.time())
        )


# ── Search history ──

def log_search(*, city: str = "lahore", area=None, property_type=None, bedrooms=None,
               price_min=None, price_max=None, furnished=None, sort=None, result_count=None):
    try:
        conn = _get_conn()
        with conn:
            conn.execute(
                "INSERT INTO search_history (city, area, property_type, bedrooms, price_min, price_max, furnished, sort, result_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (city, area, property_type, bedrooms, price_min, price_max,
                 1 if furnished else (0 if furnished is False else None),
                 sort, result_count)
            )
    except Exception:
        logger.exception("Failed to log search")


def get_popular_searches(city: str = "lahore", limit: int = 8):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT area, property_type, bedrooms, COUNT(*) as count "
        "FROM search_history "
        "WHERE city = ? AND searched_at > datetime('now', '-7 days') AND area IS NOT NULL "
        "GROUP BY area, property_type, bedrooms "
        "ORDER BY count DESC LIMIT ?",
        (city, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_searches(city: str = "lahore", limit: int = 8):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT area, property_type, bedrooms, price_min, price_max, MAX(searched_at) as searched_at "
        "FROM search_history "
        "WHERE city = ? AND area IS NOT NULL "
        "GROUP BY area, property_type, bedrooms, price_min, price_max "
        "ORDER BY searched_at DESC LIMIT ?",
        (city, limit)
    ).fetchall()
    return [dict(r) for r in rows]
