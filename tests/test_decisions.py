"""JevClient against a mocked /v1/systemone."""
import json

import httpx
import pytest

from app.decisions import DecisionError, JevClient, choice, noul, parse_decision

QUESTIONS = {
    "tenant_fit": choice("Who may rent?", {"family": "families", "bachelor": "bachelors"}),
    "backup_power": noul("Has backup power."),
}

OK_PAYLOAD = {
    "model": "jev-1.13.0",
    "answers": {
        "tenant_fit": {"type": "choice", "choice": "bachelor", "confidence": 0.9,
                       "probabilities": {"family": 0.05, "bachelor": 0.95}},
        "backup_power": {"type": "noul", "noul": 0.1},
    },
    "usage": {"input_tokens": 120, "output_tokens": 0},
}


def _client(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    return JevClient("test-key", client=httpx.AsyncClient(transport=transport), **kwargs)


class TestParseDecision:
    def test_choice_and_noul(self):
        d = parse_decision(OK_PAYLOAD)
        assert d.model == "jev-1.13.0"
        assert d.input_tokens == 120
        assert d.answers["tenant_fit"].value == "bachelor"
        assert d.answers["tenant_fit"].confidence == 0.9
        assert d.answers["backup_power"].value == 0.1
        # noul has no confidence from Jev; distance from 0.5 stands in.
        assert d.answers["backup_power"].confidence == pytest.approx(0.8)

    def test_malformed_is_not_retryable(self):
        with pytest.raises(DecisionError) as err:
            parse_decision({"answers": {"x": {"type": "choice"}}})
        assert not err.value.retryable


class TestJevClient:
    @pytest.mark.asyncio
    async def test_sends_pinned_model_state_and_key(self):
        seen = {}

        def handler(request):
            seen["auth"] = request.headers["authorization"]
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=OK_PAYLOAD)

        client = _client(handler)
        decision = await client.decide("Title: Room for bachelors", QUESTIONS)
        assert decision.answers["tenant_fit"].value == "bachelor"
        assert seen["auth"] == "Bearer test-key"
        assert seen["body"]["model"] == "jev-1.13.0"
        assert seen["body"]["state"] == "Title: Room for bachelors"
        assert seen["body"]["questions"]["backup_power"] == {"type": "noul", "instructions": "Has backup power."}

    @pytest.mark.asyncio
    async def test_retries_server_errors(self, monkeypatch):
        monkeypatch.setattr("app.decisions.asyncio.sleep", _no_sleep)
        responses = iter([httpx.Response(503), httpx.Response(429), httpx.Response(200, json=OK_PAYLOAD)])
        client = _client(lambda request: next(responses), retries=2)
        decision = await client.decide("s", QUESTIONS)
        assert decision.input_tokens == 120

    @pytest.mark.asyncio
    async def test_gives_up_after_retries(self, monkeypatch):
        monkeypatch.setattr("app.decisions.asyncio.sleep", _no_sleep)
        client = _client(lambda request: httpx.Response(502), retries=1)
        with pytest.raises(DecisionError) as err:
            await client.decide("s", QUESTIONS)
        assert err.value.retryable

    @pytest.mark.asyncio
    async def test_auth_error_is_not_retried(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(401, text="bad key")

        client = _client(handler, retries=3)
        with pytest.raises(DecisionError) as err:
            await client.decide("s", QUESTIONS)
        assert not err.value.retryable
        assert len(calls) == 1


async def _no_sleep(_seconds):
    return None
