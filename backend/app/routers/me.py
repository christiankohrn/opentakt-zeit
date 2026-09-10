from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from webauthn import options_to_json
from webauthn.helpers import bytes_to_base64url

from app.auth import as_local, bump_session_rev, current_user, local_day_bounds, now_utc, write_session
from app.balance import account_hours, days_in_range, month_days
from app.config import get_config
from app.database import get_db
from app.models import AuditEvent, Punch, User, WebAuthnCredential
from app.punches import record_punch
from app.schemas import (
    MfaVerifyIn,
    PasskeyOut,
    PasskeyRegisterVerifyIn,
    PasskeyRenameIn,
    PasswordChangeIn,
    PunchIn,
    PunchOut,
    SecurityStatusOut,
    StatusOut,
    TotpDisableIn,
    TotpEnableIn,
    TotpEnableOut,
    TotpSetupOut,
)
from app.security import hash_password, verify_password
from app.timecalc import allowed_kinds, status_from_punches
from app.totp import (
    backup_codes_remaining,
    clear_totp,
    consume_backup_code,
    generate_backup_codes,
    new_secret,
    provisioning_uri,
    qr_svg_data_uri,
    verify_code,
)
from app.webauthn_auth import registration_options, verify_registration

WEBAUTHN_REG_KEY = "webauthn_reg"
WEBAUTHN_REG_TTL = 300

router = APIRouter(prefix="/me", tags=["me"])


def _load_user(db: Session, user_id: int) -> User:
    user = db.scalar(select(User).options(selectinload(User.work_model)).where(User.id == user_id))
    assert user
    return user


def _recent_punches(db: Session, user_id: int) -> list[Punch]:
    today = as_local(now_utc()).date()
    start, _ = local_day_bounds(today - timedelta(days=2))
    rows = db.scalars(
        select(Punch)
        .where(Punch.user_id == user_id, Punch.server_time >= start)
        .order_by(Punch.server_time)
    ).all()
    return list(rows)


@router.get("/status", response_model=StatusOut)
def status(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    user = _load_user(db, actor.id)
    punches = _recent_punches(db, user.id)
    state = status_from_punches(punches)
    last = next((p for p in reversed(punches) if p.voided_at is None), None)
    cfg = get_config()
    today = as_local(now_utc()).date()
    month_start = today.replace(day=1)
    recent_start = today - timedelta(days=6)
    month_flex, total_flex = account_hours(db, user)
    days = days_in_range(db, user, min(month_start, recent_start), today)
    recent = [d for d in days if str(d.get("date", "")) >= recent_start.isoformat()]
    return StatusOut(
        state=state,
        allowed=allowed_kinds(state),
        since=last.server_time if last else None,
        display_name=user.display_name,
        org_name=cfg.org_name,
        server_time=now_utc(),
        flex_hours=month_flex,
        total_flex_hours=total_flex,
        recent_days=recent,
    )


@router.post("/punches", response_model=PunchOut)
def create_punch(payload: PunchIn, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    return record_punch(
        db,
        user,
        payload.kind,
        source="pwa",
        client_event_id=payload.client_event_id,
        device_time=payload.device_time,
        note=payload.note,
    )


@router.post("/password")
def change_password(payload: PasswordChangeIn, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user.auth_source != "local":
        raise HTTPException(400, "Passwort wird im Benutzerverzeichnis geändert")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Aktuelles Passwort stimmt nicht")
    if payload.current_password == payload.new_password:
        raise HTTPException(400, "Neues Passwort muss anders sein")
    user.password_hash = hash_password(payload.new_password)
    bump_session_rev(user)
    db.add(AuditEvent(actor_id=user.id, action="password.change", entity_type="user", entity_id=str(user.id)))
    db.commit()
    write_session(request, user)
    return {"ok": True}


@router.get("/days")
def my_days(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    user = _load_user(db, current_user(request, db).id)
    year, mon = (int(x) for x in month.split("-"))
    month_flex, total_flex = account_hours(db, user, month=month)
    return {
        "month": month,
        "days": month_days(db, user, year, mon),
        "month_flex": month_flex,
        "total_flex": total_flex,
    }


def _passkeys(db: Session, user: User) -> list[WebAuthnCredential]:
    return list(
        db.scalars(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user.id)
            .order_by(WebAuthnCredential.created_at)
        )
    )


@router.get("/security", response_model=SecurityStatusOut)
def security_status(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    return SecurityStatusOut(
        totp_enabled=bool(user.totp_enabled),
        backup_codes_remaining=backup_codes_remaining(db, user),
        can_use_password=user.auth_source == "local",
        passkeys=[PasskeyOut.model_validate(c) for c in _passkeys(db, user)],
    )


@router.post("/totp/setup", response_model=TotpSetupOut)
def totp_setup(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user.totp_enabled:
        raise HTTPException(400, "Zwei-Faktor ist bereits aktiv. Erst deaktivieren.")
    secret = new_secret()
    user.totp_secret = secret
    user.totp_confirmed_at = None
    db.commit()
    uri = provisioning_uri(secret, user.username, get_config().org_name or "Opentakt Zeit")
    return TotpSetupOut(secret=secret, otpauth_uri=uri, qr_svg=qr_svg_data_uri(uri))


@router.post("/totp/enable", response_model=TotpEnableOut)
def totp_enable(payload: TotpEnableIn, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user.totp_enabled:
        raise HTTPException(400, "Zwei-Faktor ist bereits aktiv.")
    if not user.totp_secret:
        raise HTTPException(400, "Bitte zuerst die Einrichtung starten.")
    if not verify_code(user.totp_secret, payload.code):
        raise HTTPException(400, "Code stimmt nicht. Bitte erneut versuchen.")
    user.totp_enabled = True
    user.totp_confirmed_at = now_utc()
    codes = generate_backup_codes(db, user)
    db.add(AuditEvent(actor_id=user.id, action="totp.enable", entity_type="user", entity_id=str(user.id)))
    db.commit()
    return TotpEnableOut(backup_codes=codes)


@router.post("/totp/backup-codes", response_model=TotpEnableOut)
def totp_regenerate_backup(payload: MfaVerifyIn, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(400, "Zwei-Faktor ist nicht aktiv.")
    if not (verify_code(user.totp_secret, payload.code) or consume_backup_code(db, user, payload.code)):
        raise HTTPException(400, "Code stimmt nicht.")
    codes = generate_backup_codes(db, user)
    db.add(AuditEvent(actor_id=user.id, action="totp.backup_regenerate", entity_type="user", entity_id=str(user.id)))
    db.commit()
    return TotpEnableOut(backup_codes=codes)


@router.post("/totp/disable")
def totp_disable(payload: TotpDisableIn, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user.totp_enabled:
        raise HTTPException(400, "Zwei-Faktor ist nicht aktiv.")
    if user.auth_source == "local":
        if not payload.password or not verify_password(payload.password, user.password_hash):
            raise HTTPException(400, "Aktuelles Passwort stimmt nicht.")
    if not payload.code or not (
        verify_code(user.totp_secret, payload.code) or consume_backup_code(db, user, payload.code)
    ):
        raise HTTPException(400, "Bestätigungscode stimmt nicht.")
    clear_totp(db, user)
    db.add(AuditEvent(actor_id=user.id, action="totp.disable", entity_type="user", entity_id=str(user.id)))
    db.commit()
    return {"ok": True}


@router.post("/passkeys/register/options", response_model=None)
def passkey_register_options(request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user(request, db)
    options, _ = registration_options(request, user.id, user.username, user.display_name, _passkeys(db, user))
    request.session[WEBAUTHN_REG_KEY] = {
        "challenge": bytes_to_base64url(options.challenge),
        "exp": int(now_utc().timestamp()) + WEBAUTHN_REG_TTL,
    }
    return json.loads(options_to_json(options))


@router.post("/passkeys/register/verify", response_model=PasskeyOut)
def passkey_register_verify(payload: PasskeyRegisterVerifyIn, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    pending = request.session.get(WEBAUTHN_REG_KEY)
    if not isinstance(pending, dict) or not pending.get("challenge"):
        raise HTTPException(400, "Keine Passkey-Einrichtung ausstehend.")
    if int(pending.get("exp") or 0) < int(now_utc().timestamp()):
        request.session.pop(WEBAUTHN_REG_KEY, None)
        raise HTTPException(400, "Einrichtung abgelaufen. Bitte erneut versuchen.")
    try:
        cred_id, public_key, sign_count, _ = verify_registration(request, payload.credential, pending["challenge"])
    except Exception:
        raise HTTPException(400, "Passkey konnte nicht überprüft werden.")
    request.session.pop(WEBAUTHN_REG_KEY, None)
    if db.scalar(select(WebAuthnCredential).where(WebAuthnCredential.credential_id == cred_id)):
        raise HTTPException(400, "Dieser Passkey ist bereits registriert.")
    transports = None
    resp = payload.credential.get("response") if isinstance(payload.credential, dict) else None
    if isinstance(resp, dict) and isinstance(resp.get("transports"), list):
        transports = ",".join(str(t) for t in resp["transports"])[:120]
    name = (payload.name or "Passkey").strip()[:120] or "Passkey"
    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=cred_id,
        public_key=public_key,
        sign_count=sign_count,
        transports=transports,
        name=name,
    )
    db.add(cred)
    db.add(AuditEvent(actor_id=user.id, action="passkey.register", entity_type="user", entity_id=str(user.id)))
    db.commit()
    db.refresh(cred)
    return PasskeyOut.model_validate(cred)


@router.get("/passkeys", response_model=list[PasskeyOut])
def passkey_list(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    return [PasskeyOut.model_validate(c) for c in _passkeys(db, user)]


@router.patch("/passkeys/{passkey_id}", response_model=PasskeyOut)
def passkey_rename(passkey_id: int, payload: PasskeyRenameIn, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    cred = db.get(WebAuthnCredential, passkey_id)
    if not cred or cred.user_id != user.id:
        raise HTTPException(404, "Passkey nicht gefunden.")
    cred.name = payload.name.strip()[:120] or "Passkey"
    db.commit()
    db.refresh(cred)
    return PasskeyOut.model_validate(cred)


@router.delete("/passkeys/{passkey_id}")
def passkey_delete(passkey_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    cred = db.get(WebAuthnCredential, passkey_id)
    if not cred or cred.user_id != user.id:
        raise HTTPException(404, "Passkey nicht gefunden.")
    db.delete(cred)
    db.add(AuditEvent(actor_id=user.id, action="passkey.delete", entity_type="user", entity_id=str(user.id)))
    db.commit()
    return {"ok": True}

