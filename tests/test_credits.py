import pytest

from app import credits


@pytest.fixture(autouse=True)
def schema(fresh_db):
    credits.init_credits_schema()


def test_first_balance_grants_starter_credits_once():
    assert credits.balance("client-aaaa") == credits.STARTER_CREDITS
    assert credits.balance("client-aaaa") == credits.STARTER_CREDITS


def test_spend_charges_cost_and_is_idempotent_on_ref():
    ref = credits.new_spend_ref("tailored_list")
    after = credits.spend("client-aaaa", "tailored_list", ref=ref)
    assert after == credits.STARTER_CREDITS - credits.COSTS["tailored_list"]
    assert credits.spend("client-aaaa", "tailored_list", ref=ref) == after


def test_spend_refuses_when_balance_too_low():
    for _ in range(credits.STARTER_CREDITS // credits.COSTS["tailored_list"]):
        credits.spend("client-aaaa", "tailored_list", ref=credits.new_spend_ref("tailored_list"))
    with pytest.raises(credits.InsufficientCredits) as exc:
        credits.spend("client-aaaa", "tailored_list", ref=credits.new_spend_ref("tailored_list"))
    assert exc.value.as_detail() == {
        "code": "insufficient_credits", "action": "tailored_list",
        "balance": 0, "cost": credits.COSTS["tailored_list"],
    }
    assert credits.balance("client-aaaa") == 0


def test_refund_restores_once():
    ref = credits.new_spend_ref("search_report")
    credits.spend("client-aaaa", "search_report", ref=ref)
    assert credits.refund(ref) is True
    assert credits.refund(ref) is False
    assert credits.balance("client-aaaa") == credits.STARTER_CREDITS


def test_grant_is_idempotent_on_ref():
    assert credits.grant("client-aaaa", 60, kind="purchase", ref="payment:p1") is True
    assert credits.grant("client-aaaa", 60, kind="purchase", ref="payment:p1") is False
    assert credits.balance("client-aaaa") == credits.STARTER_CREDITS + 60


def test_unknown_action_is_rejected():
    with pytest.raises(ValueError):
        credits.spend("client-aaaa", "free_lunch", ref="spend:x")


def test_spend_reference_cannot_be_reused_by_another_owner_or_action():
    credits.spend('client-aaaa', 'tailored_list', ref='spend:guard')
    for owner, action in [('client-bbbb', 'tailored_list'), ('client-aaaa', 'search_report')]:
        with pytest.raises(credits.SpendReferenceConflict):
            credits.spend(owner, action, ref='spend:guard')
    with pytest.raises(credits.SpendReferenceConflict):
        credits.spend('client-aaaa', 'tailored_list', ref='spend:guard', allow_replay=False)
