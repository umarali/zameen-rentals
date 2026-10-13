"""Credits: prepaid, one-time top-ups that pay for optional features.

There is no subscription and nothing renews. A renter buys a pack once and
spends credits on Tailored lists, Search reports and Daily shortlists. Search itself stays free. Historical action keys stay in the ledger.

Every change is a row in `credit_ledger`; the balance is the sum of `delta`
for a client. Rows are never updated or deleted. Each row may carry a `ref`,
which is unique across the table, so grants, spends and refunds are
idempotent: replaying the same ref changes nothing.

Credits are keyed by the anonymous `client_id` from personalization.py.

Usage pattern for a paid action (spend first, refund if the work fails):

    ref = credits.new_spend_ref("tailored_list")
    credits.spend(client_id, "tailored_list", ref=ref)   # may raise InsufficientCredits
    try:
        result = do_the_work()
    except Exception:
        credits.refund(ref)
        raise
"""
import logging
import uuid

from app.database import _get_conn

logger = logging.getLogger("zameenrentals")

STARTER_CREDITS = 10

# One-time packs. Prices are whole PKR. Changing these changes what the
# pricing page and checkout offer; keep docs/credits-contract.md in sync.
PACKS = {
    "standard": {"credits": 50, "price_pkr": 500},
}

# Cost in credits of each paid action.
COSTS = {
    "tailored_list": 1,
    "search_report": 1,
    "daily_shortlist_day": 1,
    "instant_alerts_day": 1,
    "listing_history": 1,
}

OFFERED_ACTIONS = ("tailored_list", "search_report", "daily_shortlist_day")


class SpendReferenceConflict(ValueError):
    """A spend reference cannot be reused for this operation."""


KINDS = ("starter", "purchase", "spend", "refund", "restore_in", "restore_out", "adjust")


class InsufficientCredits(Exception):
    def __init__(self, action: str, balance: int, cost: int):
        super().__init__(f"{action} costs {cost} credits; balance is {balance}")
        self.action = action
        self.balance = balance
        self.cost = cost

    def as_detail(self) -> dict:
        """Body for HTTP 402 responses. The frontend relies on this shape."""
        return {
            "code": "insufficient_credits",
            "action": self.action,
            "balance": self.balance,
            "cost": self.cost,
        }


def init_credits_schema(conn=None):
    """Create credit tables. Idempotent; safe on every boot."""
    conn = conn or _get_conn()
    with conn:
        conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS credit_ledger (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id  TEXT NOT NULL,
                delta      INTEGER NOT NULL,
                kind       TEXT NOT NULL CHECK (kind IN ({", ".join(repr(k) for k in KINDS)})),
                action     TEXT,
                ref        TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_ledger_ref
                ON credit_ledger(ref) WHERE ref IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_credit_ledger_client
                ON credit_ledger(client_id, id);
        """)


def new_spend_ref(action: str) -> str:
    return f"spend:{action}:{uuid.uuid4().hex}"


def _ensure_starter(conn, client_id: str):
    conn.execute(
        "INSERT OR IGNORE INTO credit_ledger (client_id, delta, kind, ref) VALUES (?, ?, 'starter', ?)",
        (client_id, STARTER_CREDITS, f"starter:{client_id}"),
    )


def _balance(conn, client_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE client_id = ?", (client_id,)
    ).fetchone()
    return int(row[0])


def balance(client_id: str) -> int:
    """Current balance. The first call for a client grants the starter credits."""
    conn = _get_conn()
    with conn:
        _ensure_starter(conn, client_id)
    return _balance(conn, client_id)


def grant(client_id: str, credits: int, *, kind: str, ref: str, action: str | None = None) -> bool:
    """Add credits. Returns False if `ref` was already used (nothing changes)."""
    if kind not in ("purchase", "restore_in", "adjust"):
        raise ValueError(f"grant cannot use kind {kind!r}")
    if credits <= 0 and kind != "adjust":
        raise ValueError("grant needs a positive amount")
    conn = _get_conn()
    with conn:
        _ensure_starter(conn, client_id)
        cur = conn.execute(
            "INSERT OR IGNORE INTO credit_ledger (client_id, delta, kind, action, ref) VALUES (?, ?, ?, ?, ?)",
            (client_id, credits, kind, action, ref),
        )
    return cur.rowcount == 1


def spend(client_id: str, action: str, *, ref: str, allow_replay: bool = True) -> int:
    """Charge COSTS[action]. Returns the new balance.

    Raises InsufficientCredits when the balance is too low. Replaying a ref
    that was already charged returns the balance without charging again.
    The balance check and the insert are one statement, so two concurrent
    spends cannot both pass the check.
    """
    if action not in COSTS:
        raise ValueError(f"unknown paid action {action!r}")
    cost = COSTS[action]
    conn = _get_conn()
    with conn:
        _ensure_starter(conn, client_id)
        existing = conn.execute("SELECT client_id, kind, action FROM credit_ledger WHERE ref = ?", (ref,)).fetchone()
        if existing:
            if not allow_replay or tuple(existing) != (client_id, "spend", action):
                raise SpendReferenceConflict("Spend reference already used")
            return _balance(conn, client_id)
        cur = conn.execute(
            """INSERT INTO credit_ledger (client_id, delta, kind, action, ref)
               SELECT ?, ?, 'spend', ?, ?
               WHERE (SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE client_id = ?) >= ?""",
            (client_id, -cost, action, ref, client_id, cost),
        )
        current = _balance(conn, client_id)
    if cur.rowcount != 1:
        raise InsufficientCredits(action, current, cost)
    return current


def refund(spend_ref: str) -> bool:
    """Reverse a spend. Returns False if there was no such spend or it was already refunded."""
    conn = _get_conn()
    with conn:
        row = conn.execute(
            "SELECT client_id, delta, action FROM credit_ledger WHERE ref = ? AND kind = 'spend'",
            (spend_ref,),
        ).fetchone()
        if not row:
            return False
        cur = conn.execute(
            "INSERT OR IGNORE INTO credit_ledger (client_id, delta, kind, action, ref) VALUES (?, ?, 'refund', ?, ?)",
            (row["client_id"], -row["delta"], row["action"], f"refund:{spend_ref}"),
        )
    return cur.rowcount == 1


def history(client_id: str, limit: int = 50) -> list[dict]:
    rows = _get_conn().execute(
        """SELECT delta, kind, action, created_at FROM credit_ledger
           WHERE client_id = ? ORDER BY id DESC LIMIT ?""",
        (client_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def summary(client_id: str) -> dict:
    """What GET /api/credits returns."""
    return {
        "balance": balance(client_id),
        "costs": {action: COSTS[action] for action in OFFERED_ACTIONS},
        "packs": [{"id": k, **v} for k, v in PACKS.items()],
        "history": history(client_id),
    }
