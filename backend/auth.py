"""Token based auth with role scoping. Standard library only.

Passwords are stored as PBKDF2-HMAC-SHA256 hashes. Session tokens are signed
with HMAC-SHA256 so they cannot be tampered with on the client.
"""

import base64
import hashlib
import hmac
import json
import os
import time

SECRET = (os.environ.get("DRISHTI_SECRET") or os.environ.get("RISKLENS_SECRET") or "drishti-dev-secret-change-in-production").encode()
TOKEN_TTL_SECONDS = 60 * 60 * 12
PBKDF2_ROUNDS = 120_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def create_token(user: dict) -> str:
    payload = {
        "sub": user["username"],
        "name": user["full_name"],
        "role": user["role"],
        "state": user.get("scope_state"),
        "district": user.get("scope_district"),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64e(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def decode_token(token: str):
    if not token or "." not in token:
        return None
    body, _, signature = token.partition(".")
    expected = _b64e(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def scope_filter(user: dict):
    """Return (sql_fragment, params) restricting rows to the user's jurisdiction."""
    role = user.get("role")
    if role == "district" and user.get("district"):
        return "w.state = ? AND w.district = ?", [user["state"], user["district"]]
    if role == "state" and user.get("state"):
        return "w.state = ?", [user["state"]]
    return "1=1", []
