"""Feedback email payload and the no-config path of the Resend notifier."""
import asyncio
import json

from app import notify


def test_payload_sets_reply_to_and_pretty_context(monkeypatch):
    monkeypatch.setenv("FEEDBACK_EMAIL_TO", "owner@example.com")
    monkeypatch.delenv("FEEDBACK_EMAIL_FROM", raising=False)
    payload = notify.feedback_email("Pins are off in DHA\nsecond line", json.dumps({"city": "karachi"}), "r@x.pk")
    assert payload["from"] == notify.DEFAULT_FROM
    assert payload["to"] == ["owner@example.com"]
    assert payload["reply_to"] == "r@x.pk"
    assert payload["subject"] == "Feedback: Pins are off in DHA"
    assert '"city": "karachi"' in payload["text"]
    assert "html" not in payload


def test_payload_without_email_or_context(monkeypatch):
    monkeypatch.setenv("FEEDBACK_EMAIL_TO", "owner@example.com")
    payload = notify.feedback_email("x" * 100, None, None)
    assert "reply_to" not in payload
    assert payload["subject"] == "Feedback: " + "x" * 60 + "…"
    assert "From: not given" in payload["text"]


def test_skips_without_configuration(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("FEEDBACK_EMAIL_TO", "owner@example.com")

    def boom(*a, **k):
        raise AssertionError("must not call the network")

    monkeypatch.setattr(notify.httpx, "AsyncClient", boom)
    assert asyncio.run(notify.notify_feedback("hi", None, None)) is False
