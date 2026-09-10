import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from webauthn import options_to_json
from webauthn.helpers import bytes_to_base64url

from app.auth import authenticate, bump_session_rev, current_user, normalize_username, now_utc, write_session
from app.database import get_db
from app.mail import (
    RESET_RESEND_MINUTES,
    find_local_user,
    lookup_mail_token,
    recent_unused_token,
    send_access_mail,
)
from app.models import AuditEvent, User, WebAuthnCredential
from app.schemas import (
    ForgotIn,
    LoginIn,
    MfaRequiredOut,
    MfaVerifyIn,
    PasskeyAuthOptionsIn,
    PasskeyAuthVerifyIn,
    ResetIn,
    ResetInfoOut,
    UserOut,
)
from app.security import hash_password
from app.totp import backup_codes_remaining, consume_backup_code, verify_code
from app.webauthn_auth import authentication_options, credential_raw_id, verify_authentication

router = APIRouter(prefix="/auth", tags=["auth"])

MFA_PENDING_KEY = "pending_mfa"
MFA_PENDING_TTL = 300  # seconds a password check stays valid before the 2FA step
MFA_MAX_ATTEMPTS = 6
WEBAUTHN_AUTH_KEY = "webauthn_auth"
WEBAUTHN_TTL = 300


def _user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


def _mfa_methods(db: Session, user: User) -> list[str]:
    methods = ["totp"]
    if backup_codes_remaining(db, user) > 0:
        methods.append("backup_code")
    return methods


@router.post("/login", response_model=None)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> UserOut | MfaRequiredOut:
    user = authenticate(db, payload.username.strip(), payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Anmeldung fehlgeschlagen")
    if not user.web_login:
        raise HTTPException(status_code=403, detail="Anmeldung nur am Terminal. Bitte Transponder verwenden.")
    if user.totp_enabled and user.totp_secret:
        request.session.clear()
        request.session[MFA_PENDING_KEY] = {
            "uid": user.id,
            "exp": int(now_utc().timestamp()) + MFA_PENDING_TTL,
            "tries": 0,
        }
        return MfaRequiredOut(methods=_mfa_methods(db, user))
    request.session.clear()
    write_session(request, user)
    db.add(AuditEvent(actor_id=user.id, action="login", entity_type="user", entity_id=str(user.id)))
    db.commit()
    return _user_out(user)


@router.post("/mfa", response_model=None)
def mfa(payload: MfaVerifyIn, request: Request, db: Session = Depends(get_db)) -> UserOut:
    pending = request.session.get(MFA_PENDING_KEY)
    if not isinstance(pending, dict) or not pending.get("uid"):
        raise HTTPException(status_code=401, detail="Keine Anmeldung ausstehend. Bitte neu anmelden.")
    if int(pending.get("exp") or 0) < int(now_utc().timestamp()):
        request.session.clear()
        raise HTTPException(status_code=401, detail="Anmeldung abgelaufen. Bitte neu anmelden.")
    user = db.get(User, int(pending["uid"]))
    if not user or not user.active or not user.web_login or not user.totp_enabled:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Anmeldung fehlgeschlagen")

    ok = verify_code(user.totp_secret, payload.code)
    used_backup = False
    if not ok:
        used_backup = consume_backup_code(db, user, payload.code)
        ok = used_backup
    if not ok:
        pending["tries"] = int(pending.get("tries") or 0) + 1
        if pending["tries"] >= MFA_MAX_ATTEMPTS:
            request.session.clear()
            db.commit()
            raise HTTPException(status_code=429, detail="Zu viele Versuche. Bitte neu anmelden.")
        request.session[MFA_PENDING_KEY] = pending
        db.commit()
        raise HTTPException(status_code=401, detail="Code ungültig")

    request.session.clear()
    write_session(request, user)
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="login",
            entity_type="user",
            entity_id=str(user.id),
            payload=json.dumps({"mfa": "backup_code" if used_backup else "totp"}),
        )
    )
    db.commit()
    return _user_out(user)


@router.post("/passkey/options", response_model=None)
def passkey_options(payload: PasskeyAuthOptionsIn, request: Request, db: Session = Depends(get_db)) -> dict:
    creds: list[WebAuthnCredential] = []
    if payload.username:
        key = normalize_username(payload.username)
        user = db.scalar(select(User).where(func.lower(User.username) == key))
        if user and user.active and user.web_login:
            creds = list(db.scalars(select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)))
    options, _ = authentication_options(request, creds)
    request.session[WEBAUTHN_AUTH_KEY] = {
        "challenge": bytes_to_base64url(options.challenge),
        "exp": int(now_utc().timestamp()) + WEBAUTHN_TTL,
    }
    return json.loads(options_to_json(options))


@router.post("/passkey/verify", response_model=None)
def passkey_verify(payload: PasskeyAuthVerifyIn, request: Request, db: Session = Depends(get_db)) -> UserOut:
    pending = request.session.get(WEBAUTHN_AUTH_KEY)
    if not isinstance(pending, dict) or not pending.get("challenge"):
        raise HTTPException(status_code=401, detail="Keine Passkey-Anmeldung ausstehend.")
    if int(pending.get("exp") or 0) < int(now_utc().timestamp()):
        request.session.clear()
        raise HTTPException(status_code=401, detail="Anmeldung abgelaufen. Bitte neu versuchen.")
    raw_id = credential_raw_id(payload.credential)
    cred = db.scalar(select(WebAuthnCredential).where(WebAuthnCredential.credential_id == raw_id)) if raw_id else None
    if not cred:
        raise HTTPException(status_code=401, detail="Passkey unbekannt")
    user = db.get(User, cred.user_id)
    if not user or not user.active or not user.web_login:
        raise HTTPException(status_code=403, detail="Anmeldung nicht möglich")
    try:
        new_count = verify_authentication(request, payload.credential, pending["challenge"], cred)
    except Exception:
        raise HTTPException(status_code=401, detail="Passkey-Anmeldung fehlgeschlagen")
    cred.sign_count = new_count
    cred.last_used_at = now_utc()
    request.session.clear()
    write_session(request, user)
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="login",
            entity_type="user",
            entity_id=str(user.id),
            payload=json.dumps({"mfa": "passkey"}),
        )
    )
    db.commit()
    return _user_out(user)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(request: Request, db: Session = Depends(get_db)):
    return current_user(request, db)


@router.post("/forgot")
def forgot(payload: ForgotIn, db: Session = Depends(get_db)):
    user = find_local_user(db, payload.username_or_email)
    if (
        user
        and user.active
        and user.web_login
        and user.auth_source == "local"
        and user.email
    ):
        if not recent_unused_token(db, user, "reset", timedelta(minutes=RESET_RESEND_MINUTES)):
            try:
                send_access_mail(db, user, purpose="reset")
                db.add(
                    AuditEvent(
                        actor_id=None,
                        action="password.forgot",
                        entity_type="user",
                        entity_id=str(user.id),
                    )
                )
                db.commit()
            except Exception:
                db.rollback()
    return {"ok": True}


@router.get("/password-token", response_model=ResetInfoOut)
def password_token_info(token: str, db: Session = Depends(get_db)):
    row = lookup_mail_token(db, token)
    if not row:
        raise HTTPException(400, "Link ist ungültig oder abgelaufen")
    user = db.get(User, row.user_id)
    if not user or not user.active:
        raise HTTPException(400, "Link ist ungültig oder abgelaufen")
    return ResetInfoOut(username=user.username, display_name=user.display_name, purpose=row.purpose)


@router.post("/password-token")
def consume_password_token(payload: ResetIn, request: Request, db: Session = Depends(get_db)):
    from app.auth import now_utc

    row = lookup_mail_token(db, payload.token)
    if not row:
        raise HTTPException(400, "Link ist ungültig oder abgelaufen")
    user = db.get(User, row.user_id)
    if not user or not user.active or user.auth_source != "local":
        raise HTTPException(400, "Link ist ungültig oder abgelaufen")
    if not user.web_login:
        raise HTTPException(400, "Keine Web-Anmeldung für diesen Benutzer")
    user.password_hash = hash_password(payload.password)
    row.used_at = now_utc()
    bump_session_rev(user)
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="password.reset" if row.purpose == "reset" else "password.invite",
            entity_type="user",
            entity_id=str(user.id),
        )
    )
    db.commit()
    request.session.clear()
    return {"ok": True}
