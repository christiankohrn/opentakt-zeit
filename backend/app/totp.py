from __future__ import annotations

import secrets
from urllib.parse import quote

import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TotpBackupCode, User
from app.security import hash_password, verify_password

BACKUP_CODE_COUNT = 10
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars (0/O, 1/I)


def new_secret() -> str:
    """A fresh base32 TOTP secret compatible with common authenticator apps."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verify_code(secret: str | None, code: str) -> bool:
    if not secret or not code:
        return False
    cleaned = code.strip().replace(" ", "")
    if not cleaned.isdigit():
        return False
    # valid_window=1 tolerates a ±30s clock skew between server and phone.
    return pyotp.TOTP(secret).verify(cleaned, valid_window=1)


def qr_svg_data_uri(uri: str) -> str:
    """Inline SVG data URI for the otpauth URI, rendered without extra deps."""
    import segno

    qr = segno.make(uri, error="m")
    svg = qr.svg_inline(scale=5, border=2)
    return "data:image/svg+xml;utf8," + quote(svg)


def _normalize_backup(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def generate_backup_codes(db: Session, user: User) -> list[str]:
    """Replace any existing backup codes with a fresh batch; return the plaintext once."""
    for row in db.scalars(select(TotpBackupCode).where(TotpBackupCode.user_id == user.id)):
        db.delete(row)
    codes: list[str] = []
    for _ in range(BACKUP_CODE_COUNT):
        raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
        db.add(TotpBackupCode(user_id=user.id, code_hash=hash_password(raw)))
    return codes


def consume_backup_code(db: Session, user: User, code: str) -> bool:
    raw = _normalize_backup(code)
    if not raw:
        return False
    for row in db.scalars(
        select(TotpBackupCode).where(TotpBackupCode.user_id == user.id, TotpBackupCode.used_at.is_(None))
    ):
        if verify_password(raw, row.code_hash):
            from app.auth import now_utc

            row.used_at = now_utc()
            return True
    return False


def backup_codes_remaining(db: Session, user: User) -> int:
    return int(
        db.query(TotpBackupCode)
        .filter(TotpBackupCode.user_id == user.id, TotpBackupCode.used_at.is_(None))
        .count()
    )


def clear_totp(db: Session, user: User) -> None:
    for row in db.scalars(select(TotpBackupCode).where(TotpBackupCode.user_id == user.id)):
        db.delete(row)
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_confirmed_at = None
