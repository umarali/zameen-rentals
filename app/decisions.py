"""Typed decisions from TypeSafe Jev (POST /v1/systemone).

Jev answers bounded questions about a text `state`: choice (one label from a
fixed set), score (position on an ordered rubric) and noul (probability that a
statement is true). It never writes free text. Callers depend on
DecisionProvider, so another decision API can replace Jev without touching them.
"""
import asyncio
import logging
import math
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


def _number(value, *, probability=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a numeric value")
    if not math.isfinite(value) or (probability and not 0 <= value <= 1):
        raise ValueError("Invalid numeric range")
    return float(value)


def _parse_answer(raw, question=None):
    if not isinstance(raw, dict):
        raise ValueError("Answer must be an object")
    kind = raw.get("type")
    if question and kind != question["type"]:
        raise ValueError("Answer type differs from requested question")
    if kind == "noul":
        p = _number(raw["noul"], probability=True)
        return Answer("noul", p, abs(p - 0.5) * 2)
    if kind not in ("choice", "score"):
        raise ValueError("Unknown answer type")
    confidence = _number(raw["confidence"], probability=True)
    probabilities = raw.get("probabilities", {})
    if not isinstance(probabilities, dict):
        raise ValueError("Probabilities must be an object")
    probabilities = {k: _number(v, probability=True) for k, v in probabilities.items()}
    if probabilities and not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.02):
        raise ValueError("Probabilities must sum to one")
    value = raw[kind]
    if kind == "choice":
        if not isinstance(value, str) or not value:
            raise ValueError("Choice must be a nonempty string")
        if question and value not in question["criteria"]:
            raise ValueError("Choice is not an allowed option")
        expected = set(question["criteria"]) if question else None
    else:
        value = _number(value)
        if value < 0 or (question and value > len(question["criteria"]) - 1):
            raise ValueError("Score is outside the rubric")
        expected = {str(i) for i in range(len(question["criteria"]))} if question else None
    if expected is not None and probabilities and set(probabilities) != expected:
        raise ValueError("Probability keys differ from the requested criteria")
    return Answer(kind, value, confidence, probabilities)


def parse_decision(payload, questions=None):
    try:
        if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
            raise ValueError("Decision answers must be an object")
        raw_answers = payload["answers"]
        if questions is not None and set(raw_answers) != set(questions):
            raise ValueError("Response must answer exactly the requested questions")
        answers = {name: _parse_answer(raw, questions[name] if questions else None)
                   for name, raw in raw_answers.items()}
        usage = payload.get("usage", {})
        if not isinstance(usage, dict):
            raise ValueError("Usage must be an object")
        tokens = usage.get("input_tokens", 0)
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            raise ValueError("Token usage must be a nonnegative integer")
        model = payload.get("model", "")
        if not isinstance(model, str) or (questions is not None and not model):
            raise ValueError("Model must be a nonempty string")
        return Decision(model=model, answers=answers, input_tokens=tokens)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise DecisionError("Malformed decision response", retryable=False) from exc


def validate_decision(decision, questions):
    """Validate even alternate providers before their answers reach storage."""
    try:
        payload = {"model": decision.model, "usage": {"input_tokens": decision.input_tokens},
                   "answers": {name: {"type": a.type, a.type: a.value,
                                       "confidence": a.confidence,
                                       "probabilities": a.probabilities}
                               for name, a in decision.answers.items()}}
        return parse_decision(payload, questions)
    except (AttributeError, TypeError) as exc:
        raise DecisionError("Malformed provider decision", retryable=False) from exc


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
                error = DecisionError(f"Jev transport error: {type(exc).__name__}")
            else:
                if resp.status_code == 200:
                    try:
                        decision = parse_decision(resp.json(), questions)
                    except ValueError as exc:
                        raise DecisionError("Jev returned invalid JSON", retryable=False) from exc
                    if self.model != "jev-latest" and self.model != "jev-preview" and decision.model != self.model:
                        raise DecisionError("Jev returned an unexpected model", retryable=False)
                    return decision
                retryable = resp.status_code == 429 or resp.status_code >= 500
                error = DecisionError(f"Jev HTTP {resp.status_code}",
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
