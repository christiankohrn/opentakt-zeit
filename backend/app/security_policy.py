from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import OrgSettings, User, WebAuthnCredential
from app.schemas import UserOut

# Erzwingbare Anmelde-Härtung je Rolle.
POLICY_ROLES = ("employee", "supervisor", "hr", "admin")
POLICY_VALUES = ("off", "totp", "passkey", "any")
_COLS = {role: f"mfa_policy_{role}" for role in POLICY_ROLES}


def _org(db: Session) -> OrgSettings:
    row = db.get(OrgSettings, 1)
    if row is None:
        row = OrgSettings(id=1)
        db.add(row)
        db.flush()
    return row


def get_policies(db: Session) -> dict[str, str]:
    row = _org(db)
    return {role: (getattr(row, _COLS[role], "off") or "off") for role in POLICY_ROLES}


def set_policies(db: Session, mapping: dict[str, str]) -> dict[str, str]:
    row = _org(db)
    for role, value in mapping.items():
        if role in _COLS and value in POLICY_VALUES:
            setattr(row, _COLS[role], value)
    db.flush()
    return get_policies(db)


def policy_for(db: Session, role: str) -> str:
    return get_policies(db).get(role, "off")


def _passkey_count(db: Session, user_id: int) -> int:
    return int(
        db.scalar(select(func.count()).select_from(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id))
        or 0
    )


def has_passkey(db: Session, user: User) -> bool:
    return _passkey_count(db, user.id) > 0


def passkey_counts(db: Session, user_ids: list[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(WebAuthnCredential.user_id, func.count())
        .where(WebAuthnCredential.user_id.in_(user_ids))
        .group_by(WebAuthnCredential.user_id)
    ).all()
    return {int(uid): int(count) for uid, count in rows}


def required_setup(db: Session, user: User) -> Optional[str]:
    """What the user must still enroll to satisfy their role policy, else None.

    Only web-login users are gated; terminal-only accounts never use the web app.
    """
    if not user.web_login or not user.active:
        return None
    policy = policy_for(db, user.role)
    if policy == "off":
        return None
    has_totp = bool(user.totp_enabled)
    if policy == "totp":
        return None if has_totp else "totp"
    if policy == "passkey":
        return None if has_passkey(db, user) else "passkey"
    if policy == "any":
        return None if (has_totp or has_passkey(db, user)) else "any"
    return None


def self_out(db: Session, user: User) -> UserOut:
    """UserOut for the authenticated user, enriched with security state."""
    out = UserOut.model_validate(user)
    return out.model_copy(
        update={
            "work_model_name": user.work_model.name if user.work_model else None,
            "passkey_count": _passkey_count(db, user.id),
            "security_setup_required": required_setup(db, user),
        }
    )
