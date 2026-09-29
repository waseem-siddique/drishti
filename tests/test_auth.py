"""Security and permission tests that do not need a database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import security  # noqa: E402


def test_password_hash_round_trip():
    stored = security.hash_password("Drishti@2026")
    assert stored.startswith("pbkdf2_sha256$")
    assert "Drishti@2026" not in stored
    assert security.verify_password("Drishti@2026", stored)
    assert not security.verify_password("wrong-password", stored)


def test_token_round_trip_and_tamper_detection():
    token = security.create_token({"sub": "1", "role": "ADMIN"}, "secret", 60)
    assert security.decode_token(token, "secret")["sub"] == "1"
    try:
        security.decode_token(token, "another-secret")
    except security.TokenError:
        pass
    else:  # pragma: no cover
        raise AssertionError("A token signed with a different secret must be rejected")


def test_expired_token_is_rejected():
    token = security.create_token({"sub": "1"}, "secret", -1)
    try:
        security.decode_token(token, "secret")
    except security.TokenError as exc:
        assert "expired" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("An expired token must be rejected")


def test_role_permissions_are_enforceable():
    assert security.has_permission("ADMIN", "admin:rules")
    assert not security.has_permission("REVIEWER", "admin:rules")
    assert not security.has_permission("AUDITOR", "cases:create")
    assert security.has_permission("REVIEWER", "cases:outcome")


def test_scopes_limit_visibility():
    assert security.scope_for("STATE", "Maharashtra", None)["mode"] == "STATE"
    assert security.scope_for("DISTRICT", "Maharashtra", "Pune")["mode"] == "DISTRICT"
    assert security.scope_for("ADMIN", None, None)["mode"] == "ALL"


def test_uploaded_filenames_are_made_safe():
    safe = security.safe_filename("../../etc/passwd")
    assert "/" not in safe
