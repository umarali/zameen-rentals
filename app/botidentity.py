"""Declared, verifiable crawler identity.

ZameenRentals identifies itself honestly: one fixed User-Agent that links to a
public /bot page, and (when a signing key is configured) a Web Bot Auth
signature on every outgoing request. Nothing here imitates a browser.

Web Bot Auth = HTTP Message Signatures (RFC 9421) with Ed25519, plus a public
key directory served at /.well-known/http-message-signatures-directory.
See https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/

The private key comes from the ZR_BOT_SIGNING_KEY environment variable: the
base64 (or base64url) of the 32-byte Ed25519 seed, or a PKCS#8 PEM. If it is
unset or invalid, requests still carry the fixed User-Agent but are unsigned.
"""
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from functools import lru_cache
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

logger = logging.getLogger("zameenrentals")

SITE_ORIGIN = "https://zameenrental.com"
BOT_INFO_URL = f"{SITE_ORIGIN}/bot"
BOT_USER_AGENT = f"ZameenRentalBot/1.0 (+{BOT_INFO_URL})"
BOT_SOURCE_IP = "165.22.91.77"
BOT_CONTACT_EMAIL = "feedback@zameenrental.com"
BOT_MAX_REQUESTS_PER_SECOND = 1.0

KEY_ENV_VAR = "ZR_BOT_SIGNING_KEY"
DIRECTORY_PATH = "/.well-known/http-message-signatures-directory"
DIRECTORY_CONTENT_TYPE = "application/http-message-signatures-directory+json"

REQUEST_SIG_LABEL = "sig1"
REQUEST_TAG = "web-bot-auth"
DIRECTORY_TAG = "http-message-signatures-directory"
REQUEST_SIG_TTL = 60          # seconds; Cloudflare recommends a short window
DIRECTORY_SIG_TTL = 300

# Signature-Agent is an sf-string: the quotes are part of the header value.
SIGNATURE_AGENT = f'"{SITE_ORIGIN}"'

_warned_unsigned = False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode_seed(raw: str) -> bytes:
    padded = raw + "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(padded)
    except ValueError:
        return base64.b64decode(padded)


@lru_cache(maxsize=4)
def _parse_key(raw: str):
    """Return an Ed25519PrivateKey for `raw`, or None if it is not valid."""
    try:
        if raw.startswith("-----BEGIN"):
            key = serialization.load_pem_private_key(raw.encode("ascii"), password=None)
            return key if isinstance(key, Ed25519PrivateKey) else None
        return Ed25519PrivateKey.from_private_bytes(_decode_seed(raw))
    except Exception:
        return None


def get_signing_key():
    """The configured private key, or None (unset or invalid)."""
    raw = os.environ.get(KEY_ENV_VAR, "").strip()
    if not raw:
        return None
    key = _parse_key(raw)
    if key is None:
        logger.error("%s is set but is not a valid Ed25519 key; requests are unsigned", KEY_ENV_VAR)
    return key


def _public_x(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return _b64url(raw)


def public_jwk(key: Ed25519PrivateKey) -> dict:
    return {"kty": "OKP", "crv": "Ed25519", "x": _public_x(key)}


def jwk_thumbprint(key: Ed25519PrivateKey) -> str:
    """RFC 7638 / RFC 8037 A.3 thumbprint: SHA-256 of the canonical JWK."""
    canonical = json.dumps(
        {"crv": "Ed25519", "kty": "OKP", "x": _public_x(key)},
        separators=(",", ":"), sort_keys=True,
    )
    return _b64url(hashlib.sha256(canonical.encode("ascii")).digest())


def _authority(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    default = {"https": 443, "http": 80}.get(parts.scheme)
    if parts.port and parts.port != default:
        return f"{host}:{parts.port}"
    return host


def _sign(key, params: str, base_lines: list) -> str:
    base = "\n".join(base_lines + [f'"@signature-params": {params}'])
    return base64.b64encode(key.sign(base.encode("ascii"))).decode("ascii")


def _params(components: str, key, created: int, ttl: int, tag: str) -> str:
    return (
        f"({components});created={created};keyid=\"{jwk_thumbprint(key)}\""
        f";alg=\"ed25519\";expires={created + ttl}"
        f";nonce=\"{_b64url(secrets.token_bytes(24))}\";tag=\"{tag}\""
    )


def sign_request_headers(url: str, headers: dict | None = None, *, now: float | None = None) -> dict:
    """Return `headers` with the fixed User-Agent and, if keyed, Web Bot Auth headers.

    Always overwrites User-Agent (one consistent identity). Sign immediately
    before sending: the signature is only valid for REQUEST_SIG_TTL seconds.
    """
    global _warned_unsigned
    out = dict(headers or {})
    out["User-Agent"] = BOT_USER_AGENT
    for stale in ("Signature", "Signature-Input", "Signature-Agent"):
        out.pop(stale, None)

    key = get_signing_key()
    if key is None:
        if not _warned_unsigned:
            _warned_unsigned = True
            logger.warning(
                "%s is not set: crawler requests are sent with the fixed User-Agent "
                "but UNSIGNED (no Web Bot Auth)", KEY_ENV_VAR,
            )
        return out

    created = int(now if now is not None else time.time())
    components = '"@authority" "signature-agent"'
    params = _params(components, key, created, REQUEST_SIG_TTL, REQUEST_TAG)
    sig = _sign(key, params, [
        f'"@authority": {_authority(url)}',
        f'"signature-agent": {SIGNATURE_AGENT}',
    ])
    out["Signature-Agent"] = SIGNATURE_AGENT
    out["Signature-Input"] = f"{REQUEST_SIG_LABEL}={params}"
    out["Signature"] = f"{REQUEST_SIG_LABEL}=:{sig}:"
    return out


def build_directory(authority: str, *, now: float | None = None):
    """Return (body_dict, headers) for the key directory, or None if no key.

    `authority` is the Host the directory was requested on; the response
    signature covers it (`"@authority";req`) as the directory spec requires.
    """
    key = get_signing_key()
    if key is None:
        return None
    created = int(now if now is not None else time.time())
    components = '"@authority";req'
    params = _params(components, key, created, DIRECTORY_SIG_TTL, DIRECTORY_TAG)
    sig = _sign(key, params, [f'"@authority";req: {authority.lower()}'])
    headers = {
        "Content-Type": DIRECTORY_CONTENT_TYPE,
        "Signature-Input": f"{REQUEST_SIG_LABEL}={params}",
        "Signature": f"{REQUEST_SIG_LABEL}=:{sig}:",
        "Cache-Control": "public, max-age=300",
    }
    return {"keys": [public_jwk(key)]}, headers


if __name__ == "__main__":
    # Generate a key pair: put the private value in the server's .env only.
    _k = Ed25519PrivateKey.generate()
    _seed = _k.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    print(f"{KEY_ENV_VAR}={base64.b64encode(_seed).decode('ascii')}")
    print(f"# public JWK: {json.dumps(public_jwk(_k))}")
    print(f"# keyid (JWK thumbprint): {jwk_thumbprint(_k)}")
