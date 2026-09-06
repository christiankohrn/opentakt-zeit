from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import authenticate, bump_session_rev, current_user, write_session
from app.database import get_db
from app.mail import (
    RESET_RESEND_MINUTES,
    find_local_user,
    lookup_mail_token,
    recent_unused_token,
    send_access_mail,
)
from app.models import AuditEvent, User
from app.schemas import ForgotIn, LoginIn, ResetIn, ResetInfoOut, UserOut
from app.security import hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = authenticate(db, payload.username.strip(), payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Anmeldung fehlgeschlagen")
    if not user.web_login:
        raise HTTPException(status_code=403, detail="Anmeldung nur am Terminal. Bitte Transponder verwenden.")
    request.session.clear()
    write_session(request, user)
    db.add(AuditEvent(actor_id=user.id, action="login", entity_type="user", entity_id=str(user.id)))
    db.commit()
    return user


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
