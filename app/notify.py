"""Owner notifications by email, sent through Resend's HTTP API.

The Droplet can't use SMTP (DigitalOcean blocks it), so mail goes over HTTPS.
Every setting comes from the environment; with no RESEND_API_KEY or
FEEDBACK_EMAIL_TO, notifications are skipped and feedback is only stored.
"""
import json
import logging
import os

import httpx

logger = logging.getLogger("zameenrentals")

RESEND_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "ZameenRentals <feedback@zameenrental.com>"


def feedback_email(message: str, context: str | None, email: str | None) -> dict:
    """Build the Resend payload for one feedback message (plain text only)."""
    first_line = message.splitlines()[0] if message else ""
    subject = "Feedback: " + (first_line[:60] + ("…" if len(first_line) > 60 else ""))
    lines = [message, "", "—", f"From: {email or 'not given'}"]
    if context:
        try:
            pretty = json.dumps(json.loads(context), indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            pretty = context
        lines += ["", "Search context:", pretty]
    payload = {
        "from": os.environ.get("FEEDBACK_EMAIL_FROM") or DEFAULT_FROM,
        "to": [os.environ["FEEDBACK_EMAIL_TO"]],
        "subject": subject,
        "text": "\n".join(lines),
    }
    if email:
        payload["reply_to"] = email
    return payload


async def notify_feedback(message: str, context: str | None, email: str | None) -> bool:
    """Email the owner about new feedback. Never raises; returns whether it sent."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key or not os.environ.get("FEEDBACK_EMAIL_TO"):
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=feedback_email(message, context, email),
            )
        if resp.status_code >= 400:
            logger.warning("Feedback email failed: %s %s", resp.status_code, resp.text[:200])
            return False
        return True
    except httpx.HTTPError as exc:
        logger.warning("Feedback email failed: %s", exc)
        return False
