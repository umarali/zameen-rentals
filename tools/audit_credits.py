#!/usr/bin/env python3
"""Read-only payment/credit reconciliation. Never grants credits or calls a provider.

Usage: python tools/audit_credits.py /path/to/zameenrentals.db
Exit 0: local ledger reconciles. Exit 1: discrepancies. Exit 2: unreadable schema.
A clean local audit does not verify the provider's settlement or refunds.
"""
import argparse
import json
import sqlite3
from pathlib import Path


def audit(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('BEGIN')  # One consistent snapshot, including WAL changes.
        rows = conn.execute('''SELECT p.id, p.status, p.credits, p.client_id,
            l.delta, l.client_id AS ledger_owner, l.kind
            FROM payments p LEFT JOIN credit_ledger l ON l.ref = 'payment:' || p.id''').fetchall()
        issues = []
        for row in rows:
            if row['status'] == 'paid' and (row['delta'] != row['credits'] or row['ledger_owner'] != row['client_id'] or row['kind'] != 'purchase'):
                issues.append({'payment_id': row['id'], 'issue': 'paid_payment_grant_mismatch'})
            elif row['status'] != 'paid' and row['delta'] is not None:
                issues.append({'payment_id': row['id'], 'issue': 'grant_without_paid_status'})
        orphaned = conn.execute('''SELECT l.ref FROM credit_ledger l LEFT JOIN payments p
            ON l.ref = 'payment:' || p.id WHERE l.kind='purchase' AND p.id IS NULL''').fetchall()
        issues.extend({'reference': row['ref'], 'issue': 'purchase_without_payment'} for row in orphaned)
        negative = conn.execute('SELECT COUNT(*) FROM (SELECT client_id FROM credit_ledger GROUP BY client_id HAVING SUM(delta)<0)').fetchone()[0]
        if negative:
            issues.append({'issue': 'negative_wallets', 'count': negative})
        bad_refunds = conn.execute('''SELECT r.ref FROM credit_ledger r LEFT JOIN credit_ledger s
            ON s.ref = substr(r.ref, 8) AND s.kind='spend'
            WHERE r.kind='refund' AND (s.ref IS NULL OR r.delta != -s.delta OR r.client_id != s.client_id)''').fetchall()
        issues.extend({'reference': row['ref'], 'issue': 'spend_refund_mismatch'} for row in bad_refunds)
        pending = conn.execute("SELECT COUNT(*) FROM payments WHERE status IN ('pending','expired','failed') AND provider_ref IS NOT NULL").fetchone()[0]
        return {'local_ledger_ok': not issues, 'payment_count': len(rows), 'issues': issues,
                'unpaid_payments_with_provider_reference': pending,
                'provider_settlement_verified': False, 'cash_refunds_verified': False}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.database)
    except (sqlite3.Error, OSError):
        print(json.dumps({'error': 'Cannot read the credits/payment schema; check the database path and permissions.'}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['local_ledger_ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
