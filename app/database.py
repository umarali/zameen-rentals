"""SQLite database for persistent cache, search history, and listing storage."""
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
            -- Legacy cache (kept for backward compat during migration)
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

            -- ── Structured listings table ──
            CREATE TABLE IF NOT EXISTS listings (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                zameen_id          TEXT UNIQUE NOT NULL,
                url                TEXT NOT NULL,
                title              TEXT,
                price              INTEGER,
                price_text         TEXT,
                bedrooms           INTEGER,
                bathrooms          INTEGER,
                area_size          TEXT,
                area_size_sqft     REAL,
                location           TEXT,
                image_url          TEXT,
                images_json        TEXT,
                property_type      TEXT,
                added_text         TEXT,
                phone              TEXT,
                description        TEXT,
                features_json      TEXT,
                amenities_json     TEXT,
                details_json       TEXT,
                agent_name         TEXT,
                agent_agency       TEXT,
                detail_images_json TEXT,
                city               TEXT NOT NULL,
                area_name          TEXT,
                area_slug          TEXT,
                latitude           REAL,
                longitude          REAL,
                first_seen_at      TEXT NOT NULL DEFAULT (datetime('now')),
                card_scraped_at    TEXT,
                detail_scraped_at  TEXT,
                last_seen_at       TEXT NOT NULL DEFAULT (datetime('now')),
                is_active          INTEGER NOT NULL DEFAULT 1,
                content_hash       TEXT,
                detail_hash        TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(city);
            CREATE INDEX IF NOT EXISTS idx_listings_city_area ON listings(city, area_name);
            CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price);
            CREATE INDEX IF NOT EXISTS idx_listings_bedrooms ON listings(bedrooms);
            CREATE INDEX IF NOT EXISTS idx_listings_type ON listings(property_type);
            CREATE INDEX IF NOT EXISTS idx_listings_active ON listings(is_active);
            CREATE INDEX IF NOT EXISTS idx_listings_zameen_id ON listings(zameen_id);
            CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen_at);
            CREATE INDEX IF NOT EXISTS idx_listings_detail ON listings(detail_scraped_at);

            -- ── Crawl state per area ──
            CREATE TABLE IF NOT EXISTS crawl_state (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                city            TEXT NOT NULL,
                area_name       TEXT NOT NULL,
                area_slug       TEXT NOT NULL,
                area_id         INTEGER NOT NULL,
                last_crawl_at   TEXT,
                pages_crawled   INTEGER DEFAULT 0,
                listings_found  INTEGER DEFAULT 0,
                new_listings    INTEGER DEFAULT 0,
                updated_listings INTEGER DEFAULT 0,
                crawl_status    TEXT DEFAULT 'pending',
                error_message   TEXT,
                priority        INTEGER DEFAULT 50,
                UNIQUE(city, area_slug)
            );
            CREATE INDEX IF NOT EXISTS idx_crawl_priority ON crawl_state(priority, last_crawl_at);

            -- ── Crawl audit log ──
            CREATE TABLE IF NOT EXISTS crawl_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at       TEXT NOT NULL DEFAULT (datetime('now')),
                finished_at      TEXT,
                crawl_type       TEXT NOT NULL,
                areas_crawled    INTEGER DEFAULT 0,
                pages_fetched    INTEGER DEFAULT 0,
                listings_added   INTEGER DEFAULT 0,
                listings_updated INTEGER DEFAULT 0,
                listings_removed INTEGER DEFAULT 0,
                errors           INTEGER DEFAULT 0,
                status           TEXT DEFAULT 'running'
            );
        """)

        # Set up FTS5 for full-text search on listings
        # Check if FTS table exists first (CREATE VIRTUAL TABLE doesn't support IF NOT EXISTS in all SQLite versions)
        fts_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='listings_fts'"
        ).fetchone()
        if not fts_exists:
            conn.executescript("""
                CREATE VIRTUAL TABLE listings_fts USING fts5(
                    title, location, description, area_name, property_type,
                    content='listings', content_rowid='id'
                );

                CREATE TRIGGER listings_fts_insert AFTER INSERT ON listings BEGIN
                    INSERT INTO listings_fts(rowid, title, location, description, area_name, property_type)
                    VALUES (new.id, new.title, new.location, new.description, new.area_name, new.property_type);
                END;

                CREATE TRIGGER listings_fts_delete AFTER DELETE ON listings BEGIN
                    INSERT INTO listings_fts(listings_fts, rowid, title, location, description, area_name, property_type)
                    VALUES ('delete', old.id, old.title, old.location, old.description, old.area_name, old.property_type);
                END;

                CREATE TRIGGER listings_fts_update AFTER UPDATE ON listings BEGIN
                    INSERT INTO listings_fts(listings_fts, rowid, title, location, description, area_name, property_type)
                    VALUES ('delete', old.id, old.title, old.location, old.description, old.area_name, old.property_type);
                    INSERT INTO listings_fts(rowid, title, location, description, area_name, property_type)
                    VALUES (new.id, new.title, new.location, new.description, new.area_name, new.property_type);
                END;
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
