"""Typed decisions from TypeSafe Jev (POST /v1/systemone).

Jev answers bounded questions about a text `state`: choice (one label from a
fixed set), score (position on an ordered rubric) and noul (probability that a
statement is true). It never writes free text. Callers depend on
DecisionProvider, so another decision API can replace Jev without touching them.
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger("zameenrentals")

JEV_URL = os.environ.get("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")
# Pinned: "jev-latest" moves under us and would silently change stored tags.
JEV_MODEL = os.environ.get("TYPESAFE_MODEL", "jev-1.13.0")
JEV_USD_PER_MILLION_INPUT = 0.042  # list price, 2026-09; output tokens are free


class DecisionError(Exception):
    """A decision request failed. `retryable` is False for auth/quota/bad-request errors."""

    def __init__(self, message, *, retryable=True):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class Answer:
    type: str                 # "choice" | "score" | "noul"
    value: object             # choice key, score position, or noul probability
    confidence: float         # 0..1
    probabilities: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    model: str
    answers: dict
    input_tokens: int = 0


class DecisionProvider(Protocol):
    async def decide(self, state: str, questions: dict) -> Decision: ...


def choice(instructions, criteria):
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}


def score(instructions, criteria):
    return {"type": "score", "instructions": instructions, "criteria": list(criteria)}


def noul(instructions):
    return {"type": "noul", "instructions": instructions}


def _parse_answer(raw):
    kind = raw.get("type")
    if kind == "noul":
        p = float(raw["noul"])
        # Jev returns no confidence for noul; distance from a coin flip stands in.
        return Answer("noul", p, abs(p - 0.5) * 2)
    if kind in ("choice", "score"):
        return Answer(kind, raw[kind], float(raw.get("confidence", 0.0)),
                      raw.get("probabilities") or {})
    raise DecisionError(f"Unknown answer type {kind!r}", retryable=False)


def parse_decision(payload):
    try:
        answers = {name: _parse_answer(raw) for name, raw in payload["answers"].items()}
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionError(f"Malformed decision response: {exc}", retryable=False) from exc
    usage = payload.get("usage") or {}
    return Decision(model=payload.get("model", ""), answers=answers,
                    input_tokens=int(usage.get("input_tokens") or 0))


class JevClient:
    def __init__(self, api_key, *, model=JEV_MODEL, url=JEV_URL, timeout=10.0,
                 retries=2, client=None):
        self._api_key = api_key
        self.model = model
        self._url = url
        self._retries = retries
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def decide(self, state, questions):
        body = {"model": self.model, "state": state, "questions": questions}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        for attempt in range(self._retries + 1):
            try:
                resp = await self._client.post(self._url, json=body, headers=headers)
            except httpx.TransportError as exc:
                error = DecisionError(f"Jev transport error: {exc}")
            else:
                if resp.status_code == 200:
                    return parse_decision(resp.json())
                retryable = resp.status_code == 429 or resp.status_code >= 500
                error = DecisionError(f"Jev HTTP {resp.status_code}: {resp.text[:200]}",
                                      retryable=retryable)
            if not error.retryable or attempt == self._retries:
                raise error
            await asyncio.sleep(0.5 * 2 ** attempt)

    async def aclose(self):
        await self._client.aclose()


def jev_from_env(**kwargs):
    """A JevClient when TYPESAFE_API_KEY is set, else None (features stay off)."""
    key = os.environ.get("TYPESAFE_API_KEY")
    return JevClient(key, **kwargs) if key else None
