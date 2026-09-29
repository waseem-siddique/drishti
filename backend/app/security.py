"""Password hashing, session tokens, checksums and the permission matrix."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, secrets, time
from typing import Any, Dict, Optional, Set

PBKDF2_ITERATIONS = 240_000
SALT_BYTES = 16


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(iterations))
        return hmac.compare_digest(candidate, _unb64(digest))
    except (ValueError, TypeError):
        return False


class TokenError(Exception):
    pass


def create_token(claims: Dict[str, Any], secret: str, minutes: int) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = dict(claims)
    body["iat"] = int(time.time())
    body["exp"] = int(time.time()) + minutes * 60
    payload = _b64(json.dumps(body, separators=(",", ":")).encode())
    signature = _b64(hmac.new(secret.encode(), f"{header}.{payload}".encode(),
                              hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_token(token: str, secret: str) -> Dict[str, Any]:
    try:
        header, payload, signature = token.split(".")
    except ValueError as exc:
        raise TokenError("That session token is malformed.") from exc
    expected = _b64(hmac.new(secret.encode(), f"{header}.{payload}".encode(),
                             hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature):
        raise TokenError("That session token is not valid.")
    claims = json.loads(_unb64(payload))
    if claims.get("exp", 0) < int(time.time()):
        raise TokenError("Your session has expired. Please sign in again.")
    return claims


def file_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_filename(filename: str) -> str:
    base = os.path.basename(filename or "upload").replace("\\", "_")
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in base)[:120]
    return f"{secrets.token_hex(8)}_{cleaned or 'upload'}"


ROLE_LABELS = {"ADMIN": "Administrator", "MINISTRY": "Ministry / national",
               "STATE": "State nodal officer", "DISTRICT": "District officer",
               "REVIEWER": "Reviewer", "AUDITOR": "Auditor (read only)"}
READ = {"works:read", "risk:read", "cases:read", "analytics:read", "quality:read",
        "notifications:read"}
PERMISSIONS: Dict[str, Set[str]] = {
    "ADMIN": READ | {"risk:analyse", "cases:create", "cases:assign", "cases:update",
                     "cases:outcome", "evidence:upload", "ingestion:upload", "admin:users",
                     "admin:rules", "admin:config", "audit:read"},
    "MINISTRY": READ | {"risk:analyse", "cases:create", "cases:assign", "audit:read"},
    "STATE": READ | {"risk:analyse", "cases:create", "cases:assign", "cases:update",
                     "ingestion:upload"},
    "DISTRICT": READ | {"cases:create", "cases:update", "evidence:upload"},
    "REVIEWER": READ | {"cases:update", "cases:outcome", "evidence:upload"},
    "AUDITOR": READ | {"audit:read"},
}
SCOPE_BY_ROLE = {"ADMIN": "ALL", "MINISTRY": "ALL", "AUDITOR": "ALL", "STATE": "STATE",
                 "DISTRICT": "DISTRICT", "REVIEWER": "ASSIGNED_OR_DISTRICT"}


def permissions_for(role: str) -> Set[str]:
    return PERMISSIONS.get(role, set())


def has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for(role)


def scope_for(role: str, state: Optional[str], district: Optional[str]) -> Dict[str, Any]:
    return {"mode": SCOPE_BY_ROLE.get(role, "DISTRICT"), "state": state, "district": district}
