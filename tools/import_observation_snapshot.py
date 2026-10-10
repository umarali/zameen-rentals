"""
Import Added/Updated labels from a frozen snapshot export into listing_observations.

The export (docs/listing-trust-2026-10-10/evidence/added_text_oct7_vs_current.csv.gz)
holds two observations per listing from the local crawler: the Oct-7 database
copy (oct7_*) and the Oct-10 capture (cur_*). Each becomes its own
'snapshot_import' row at its original scrape time, with provenance naming the
file, its SHA-256 and the column set. Nothing is inferred between the two.

Re-running is safe: an observation already imported is skipped.

Caveat from the review: the crawler keeps an old label when a later card has
no Added text, so a label can carry a later scrape time than when it was shown.

Usage:
  python tools/import_observation_snapshot.py PATH.csv[.gz] --dry-run
  python tools/import_observation_snapshot.py PATH.csv[.gz]

ZAMEENRENTALS_DB_DIR picks the database, as for the app.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import _get_conn, close_db, init_db  # noqa: E402
from app.listing_observations import record_observation, utc_iso  # noqa: E402

TOOL_VERSION = 1
PREFIXES = ("oct7", "cur")


def read_rows(path):
    raw = path.read_bytes()
    text = gzip.decompress(raw) if path.suffix == ".gz" else raw
    return hashlib.sha256(text).hexdigest(), list(csv.DictReader(io.StringIO(text.decode("utf-8"))))


def observations(rows, *, file_name, sha256):
    """Yield (zameen_id, fields, observed_at, provenance) for every labelled observation."""
    for row in rows:
        for prefix in PREFIXES:
            seen = row.get(f"{prefix}_card_scraped_at")
            fields = {
                "added_text": row.get(f"{prefix}_added_text") or None,
                "updated_text": row.get(f"{prefix}_updated_text") or None,
            }
            if not seen or not any(fields.values()):
                continue
            provenance = json.dumps({"file": file_name, "sha256": sha256, "columns": prefix,
                                     "tool": "import_observation_snapshot", "version": TOOL_VERSION},
                                    sort_keys=True)
            yield row["zameen_id"], fields, utc_iso(seen), provenance


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sha256, rows = read_rows(args.path)
    file_name = args.path.name.removesuffix(".gz")
    todo = list(observations(rows, file_name=file_name, sha256=sha256))
    print(f"{args.path}: sha256 {sha256} (uncompressed), {len(rows)} rows, {len(todo)} observations")
    if args.dry_run:
        return

    init_db()
    conn = _get_conn()
    counts = {"inserted": 0, "duplicate": 0}
    try:
        with conn:
            for zameen_id, fields, observed_at, provenance in todo:
                result = record_observation(conn, zameen_id, "snapshot_import", fields,
                                            observed_at=observed_at, provenance=provenance,
                                            merge=False)
                counts[result] += 1
    finally:
        close_db()
    print(f"inserted {counts['inserted']}, already present {counts['duplicate']}")


if __name__ == "__main__":
    main()
