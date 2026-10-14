from app import credits, payments, database
from tools.audit_credits import audit


def test_audit_detects_orphaned_grants_without_changing_the_database(fresh_db):
    credits.init_credits_schema()
    payments.init_payments_schema()
    credits.grant('audit-client', 50, kind='purchase', ref='payment:missing')
    conn = database._get_conn()
    before = conn.execute('SELECT COUNT(*) FROM credit_ledger').fetchone()[0]
    result = audit(database._DB_PATH)
    assert result['local_ledger_ok'] is False
    assert result['issues'] == [{'reference': 'payment:missing', 'issue': 'purchase_without_payment'}]
    assert conn.execute('SELECT COUNT(*) FROM credit_ledger').fetchone()[0] == before


def test_audit_clean_ledger_does_not_claim_provider_or_cash_refund_verification(fresh_db):
    credits.init_credits_schema()
    payments.init_payments_schema()
    assert audit(database._DB_PATH) == {'local_ledger_ok': True, 'payment_count': 0, 'issues': [],
        'unpaid_payments_with_provider_reference': 0, 'provider_settlement_verified': False, 'cash_refunds_verified': False}
