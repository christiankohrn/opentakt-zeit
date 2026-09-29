from __future__ import annotations

import hashlib
import hmac

import bcrypt


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def hash_secret(value: str) -> str:
    """API-Secret als SHA-256-Hex ablegen, damit ein DB-Abzug es nicht verrät."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_secret_hash(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def check_secret(provided: str, stored: str) -> bool:
    """Secret prüfen; gespeicherter Wert darf Hash oder (Config-Fallback) Klartext sein."""
    provided = (provided or "").strip()
    stored = (stored or "").strip()
    if not provided or not stored:
        return False
    candidate = hash_secret(provided) if is_secret_hash(stored) else provided
    left = candidate.encode("utf-8")
    right = stored.encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)
