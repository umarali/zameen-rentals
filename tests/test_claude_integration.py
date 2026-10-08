"""Provider-boundary checks; no API key or live model is needed."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
import anthropic
import httpx
import instructor

from app import parsing


@pytest.fixture
def provider(monkeypatch):
    client = Mock()
    client.messages.create = AsyncMock()
    monkeypatch.setattr(parsing, "_get_instructor_client", lambda: client)
    monkeypatch.setattr(parsing, "cache_get", lambda key: None)
    monkeypatch.setattr(parsing, "cache_set", Mock())
    return client.messages.create


def test_unknown_model_area_is_removed(provider):
    provider.return_value = parsing.RentalFilters(area="Totally Fictional District Xyzzy")
    result = asyncio.run(parsing.parse_query_with_claude("near my office"))
    assert "area" not in result
    assert result["parser"] == "ai"


def test_reversed_model_price_bounds_fall_back(provider):
    provider.return_value = parsing.RentalFilters(price_min=90000, price_max=30000)
    result = asyncio.run(parsing.parse_query_with_claude("flat under 60k"))
    assert result["price_max"] == 60000
    assert "price_min" not in result
    assert result.get("parser") != "ai"


def test_equal_price_bounds_are_valid(provider):
    provider.return_value = parsing.RentalFilters(price_min=50000, price_max=50000)
    result = asyncio.run(parsing.parse_query_with_claude("flat for exactly 50k"))
    assert result["price_min"] == result["price_max"] == 50000
    assert result["parser"] == "ai"


def test_initialization_failure_uses_regex(monkeypatch):
    monkeypatch.setattr(parsing, "_get_instructor_client", Mock(side_effect=RuntimeError("init failed")))
    result = asyncio.run(parsing.parse_query_with_claude("2 bed flat under 50k"))
    assert result["bedrooms"] == 2
    assert result["price_max"] == 50000


@pytest.mark.parametrize("error", [TimeoutError("slow"), RuntimeError("unavailable")])
def test_provider_failure_uses_regex(provider, error):
    provider.side_effect = error
    result = asyncio.run(parsing.parse_query_with_claude("2 bed flat under 50k"))
    assert result["bedrooms"] == 2
    assert result["price_max"] == 50000


def test_deadline_cancels_provider_and_does_not_cache(provider):
    cancelled = []

    async def slow(**kwargs):
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(True)

    provider.side_effect = slow

    async def run():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(parsing.parse_query_with_claude("flat"), timeout=0.02)

    asyncio.run(run())
    assert cancelled == [True]
    parsing.cache_set.assert_not_called()


def test_failed_response_is_not_cached(provider):
    provider.side_effect = RuntimeError("unavailable")
    asyncio.run(parsing.parse_query_with_claude("flat"))
    parsing.cache_set.assert_not_called()


def test_retry_budget_is_explicit(provider):
    provider.return_value = parsing.RentalFilters(property_type="apartment")
    asyncio.run(parsing.parse_query_with_claude("flat"))
    assert provider.call_args.kwargs["max_retries"] == 1


def test_model_is_configurable_and_part_of_cache_key(provider, monkeypatch):
    keys = []
    monkeypatch.setattr(parsing, "cache_get", lambda key: keys.append(key))
    provider.return_value = parsing.RentalFilters()
    for model in ("model-a", "model-b"):
        monkeypatch.setenv("CLAUDE_NLQ_MODEL", model)
        asyncio.run(parsing.parse_query_with_claude("flat"))
        assert provider.call_args.kwargs["model"] == model
    assert keys[0] != keys[1]


def test_no_key_uses_regex(monkeypatch):
    monkeypatch.setattr(parsing, "_instructor_client", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = asyncio.run(parsing.parse_query_with_claude("2 bed flat under 50k"))
    assert result["bedrooms"] == 2
    assert result["price_max"] == 50000


def test_real_sdk_and_instructor_parse_tool_response(monkeypatch):
    """Exercise the installed SDK/schema adapter, not only a fake provider."""
    seen = []

    def respond(request):
        import json
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant",
            "model": body["model"], "stop_reason": "tool_use", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
            "content": [{"type": "tool_use", "id": "tool_test", "name": "RentalFilters",
                         "input": {"bedrooms": 2, "price_max": 50000, "area": "Clifton"}}],
        })

    async def run():
        async with anthropic.AsyncAnthropic(
            api_key="test-only", max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        ) as sdk:
            monkeypatch.setattr(parsing, "_get_instructor_client", lambda: instructor.from_anthropic(sdk))
            monkeypatch.setattr(parsing, "cache_get", lambda key: None)
            result = await parsing.parse_query_with_claude("2 bed flat in Clifton under 50k", "karachi")
            assert result["parser"] == "ai"
            assert result["area"] == "Clifton"
            assert result["price_max"] == 50000

    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0]["tools"][0]["name"] == "RentalFilters"


def test_shutdown_closes_client_and_resets_singleton(monkeypatch):
    client = Mock()
    client.client.close = AsyncMock()
    monkeypatch.setattr(parsing, "_instructor_client", client)
    asyncio.run(parsing.close_nlq_client())
    client.client.close.assert_awaited_once()
    assert parsing._instructor_client is None
