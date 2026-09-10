from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import HR_ROLES, as_local, bump_session_rev, current_user, local_day_bounds, normalize_username, now_utc, require_admin, require_hr, write_session
from app.balance import account_hours, days_in_range, summarize_user_day
from app.datafox import normalize_badge
from app.database import get_db
from app.models import Absence, AuditEvent, DayAcceptance, Punch, User, WorkModel, WorkModelAssignment
from app.schemas import (
    AbsenceRangeIn,
    CalendarIn,
    CalendarOut,
    CorrectionIn,
    DayAcceptIn,
    DayReplaceIn,
    OrgSettingsIn,
    OrgSettingsOut,
    SecurityPolicyIn,
    SecurityPolicyOut,
    SmtpSettingsIn,
    SmtpTestIn,
    UserAccountIn,
    UserCreateOut,
    UserOut,
    UserSettingsIn,
    UserWrite,
    WorkModelAssignIn,
    WorkModelAssignOut,
    WorkModelIn,
    WorkModelOut,
)
from app.security import hash_password
from app.security_policy import POLICY_ROLES, POLICY_VALUES, get_policies, passkey_counts, set_policies
from app.holidays import STATES, bundesland_of, calendar_map
from app.mail import MailError, apply_smtp, has_open_invite, normalize_email, send_access_mail, send_test_mail, smtp_ready, smtp_status, valid_email
from app.timecalc import punches_window_for_month, summarize_day
from app.workmodels import (
    ensure_initial_assignment,
    load_timeline,
    load_timelines,
    model_for,
    sync_current_model,
    upsert_assignment,
)

router = APIRouter(prefix="/hr", tags=["hr"])

_WARN_DE = {
    "checkout_missing": "Gehen fehlt",
    "break_short": "Pause unter 30 Min.",
    "break_short_9h": "Pause unter 45 Min. (ab 9 Std.)",
    "break_long": "Pause über 90 Min.",
    "over_10h": "Mehr als 10 Stunden",
    "missing_day": "Keine Buchung (Werktag)",
    "overnight": "Schicht über Mitternacht",
}


def _warn_de(code: str) -> str:
    return _WARN_DE.get(code, code)


def _actor(request: Request, db: Session) -> User:
    return require_hr(current_user(request, db))


def _actor_admin(request: Request, db: Session) -> User:
    return require_admin(_actor(request, db))


def _active_admin_count(db: Session) -> int:
    return int(
        db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.active.is_(True))) or 0
    )


LAST_ADMIN_MSG = "Der letzte Administrator kann nicht deaktiviert oder herabgestuft werden"
ADMIN_ROLE_MSG = "Nur Administrator darf Rollen ändern"
ADMIN_ACTIVE_MSG = "Nur Administrator darf Konten deaktivieren oder aktivieren"
ADMIN_PASSWORD_MSG = "Nur Administrator darf Passwörter anderer Benutzer setzen"
ADMIN_WEB_LOGIN_MSG = "Nur Administrator darf die Web-Anmeldung ändern"


def _ensure_not_last_admin(db: Session, user: User, new_role: str, new_active: bool) -> None:
    if user.role != "admin":
        return
    if new_role == "admin" and new_active:
        return
    if _active_admin_count(db) <= 1:
        raise HTTPException(400, LAST_ADMIN_MSG)


def _require_admin_for(actor: User, changing: bool, detail: str) -> None:
    if changing and actor.role != "admin":
        raise HTTPException(403, detail)


def _clear_acceptance(db: Session, user_id: int, day: date) -> None:
    row = db.scalar(select(DayAcceptance).where(DayAcceptance.user_id == user_id, DayAcceptance.day == day))
    if row:
        db.delete(row)


def _attach_accepted(summary: dict, acc: DayAcceptance | None) -> dict:
    if acc:
        summary["accepted"] = {"reason": acc.reason, "at": acc.accepted_at.isoformat()}
    else:
        summary["accepted"] = None
    return summary


def _user_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    return out.model_copy(update={"work_model_name": user.work_model.name if user.work_model else None})


def _clean_transponder(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().replace(" ", "").replace(":", "").replace("-", "")
    return cleaned or None


def _web_login_for(role: str, web_login: bool) -> bool:
    if role in HR_ROLES:
        return True
    return web_login


def _transponder_taken(db: Session, value: str, exclude_id: int | None = None) -> bool:
    keys = normalize_badge(value)
    if not keys:
        return False
    users = db.scalars(select(User).where(User.transponder_id.is_not(None)))
    for other in users:
        if exclude_id is not None and other.id == exclude_id:
            continue
        if normalize_badge(other.transponder_id or "") & keys:
            return True
    return False


def _set_transponder(db: Session, user: User, value: str | None) -> None:
    cleaned = _clean_transponder(value)
    if cleaned and _transponder_taken(db, cleaned, exclude_id=user.id):
        raise HTTPException(409, "Transpondernummer ist bereits vergeben")
    user.transponder_id = cleaned


def _require_password(role: str, web_login: bool, password: str | None, has_hash: bool) -> None:
    if _web_login_for(role, web_login) and not password and not has_hash:
        raise HTTPException(400, "Passwort für die Web-Anmeldung erforderlich")


def _set_email(value: str | None) -> str | None:
    email = normalize_email(value)
    if email and not valid_email(email):
        raise HTTPException(400, "E-Mail-Adresse ist ungültig")
    return email


def _check_employment_dates(user: User) -> None:
    start = user.hired_on
    if start is None and user.created_at:
        start = as_local(user.created_at).date()
    if start and user.left_on and user.left_on < start:
        raise HTTPException(400, "Austritt liegt vor dem Eintritt")


@router.get("/users", response_model=list[UserOut])
def list_users(request: Request, db: Session = Depends(get_db)):
    _actor(request, db)
    users = list(db.scalars(select(User).options(selectinload(User.work_model)).order_by(User.display_name)))
    counts = passkey_counts(db, [u.id for u in users])
    return [_user_out(u).model_copy(update={"passkey_count": counts.get(u.id, 0)}) for u in users]


@router.post("/users", response_model=UserCreateOut)
def create_user(payload: UserWrite, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    _require_admin_for(actor, payload.role != "employee", ADMIN_ROLE_MSG)
    _require_admin_for(actor, not payload.active, ADMIN_ACTIVE_MSG)
    _require_admin_for(actor, bool(payload.password), ADMIN_PASSWORD_MSG)
    _require_admin_for(actor, bool(payload.web_login) or bool(payload.send_access_mail), ADMIN_WEB_LOGIN_MSG)
    username = normalize_username(payload.username)
    if db.scalar(select(User).where(func.lower(User.username) == username)):
        raise HTTPException(409, "Benutzername vergeben")
    web_login = _web_login_for(payload.role, payload.web_login)
    email = _set_email(payload.email)
    if payload.send_access_mail:
        if not web_login:
            raise HTTPException(400, "Zugangsdaten per Mail nur bei Web-Anmeldung")
        if not email:
            raise HTTPException(400, "Gültige E-Mail-Adresse erforderlich")
        if not smtp_ready(db):
            raise HTTPException(400, "Mailserver ist nicht eingerichtet")
    else:
        _require_password(payload.role, web_login, payload.password, False)
    user = User(
        username=username,
        display_name=payload.display_name.strip(),
        email=email,
        role=payload.role,
        active=payload.active,
        work_model_id=payload.work_model_id,
        auth_source="local",
        password_hash=hash_password(payload.password) if payload.password else None,
        auto_break=payload.auto_break,
        web_login=web_login,
        hired_on=payload.hired_on or as_local(now_utc()).date(),
        left_on=payload.left_on,
    )
    _check_employment_dates(user)
    _set_transponder(db, user, payload.transponder_id)
    db.add(user)
    db.flush()
    if user.work_model_id:
        ensure_initial_assignment(db, user)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="user.create",
            entity_type="user",
            entity_id=str(user.id),
            payload=json.dumps({"username": user.username, "role": user.role}),
        )
    )
    db.commit()
    db.refresh(user)
    mail_sent = None
    mail_error = None
    if payload.send_access_mail:
        try:
            send_access_mail(db, user, purpose="invite")
            db.add(
                AuditEvent(
                    actor_id=actor.id,
                    action="user.invite",
                    entity_type="user",
                    entity_id=str(user.id),
                )
            )
            db.commit()
            mail_sent = True
        except MailError as exc:
            db.rollback()
            mail_sent = False
            mail_error = str(exc)
    out = _user_out(user)
    return UserCreateOut(**out.model_dump(), mail_sent=mail_sent, mail_error=mail_error)


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_user(user_id: int, payload: UserWrite, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    next_web_login = _web_login_for(
        payload.role,
        payload.web_login if "web_login" in payload.model_fields_set else user.web_login,
    )
    _require_admin_for(actor, payload.role != user.role, ADMIN_ROLE_MSG)
    _require_admin_for(actor, payload.active != user.active, ADMIN_ACTIVE_MSG)
    _require_admin_for(actor, bool(payload.password), ADMIN_PASSWORD_MSG)
    _require_admin_for(actor, next_web_login != user.web_login, ADMIN_WEB_LOGIN_MSG)
    _ensure_not_last_admin(db, user, payload.role, payload.active)
    privileged = payload.role != user.role or payload.active != user.active or bool(payload.password) or next_web_login != user.web_login
    user.username = normalize_username(payload.username)
    user.display_name = payload.display_name.strip()
    user.email = _set_email(payload.email)
    user.role = payload.role
    user.active = payload.active
    if payload.work_model_id and payload.work_model_id != user.work_model_id:
        try:
            upsert_assignment(db, user, payload.work_model_id, as_local(now_utc()).date(), actor.id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    elif payload.work_model_id is None:
        user.work_model_id = None
    user.auto_break = payload.auto_break
    user.web_login = next_web_login
    if "transponder_id" in payload.model_fields_set:
        _set_transponder(db, user, payload.transponder_id)
    _require_password(
        payload.role,
        user.web_login,
        payload.password,
        bool(user.password_hash) or has_open_invite(db, user),
    )
    if payload.password:
        user.password_hash = hash_password(payload.password)
        user.auth_source = "local"
    if "hired_on" in payload.model_fields_set:
        user.hired_on = payload.hired_on
    if "left_on" in payload.model_fields_set:
        user.left_on = payload.left_on
    _check_employment_dates(user)
    if privileged:
        bump_session_rev(user)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="user.update",
            entity_type="user",
            entity_id=str(user.id),
        )
    )
    db.commit()
    db.refresh(user)
    if actor.id == user.id:
        write_session(request, user)
    return _user_out(user)


@router.patch("/users/{user_id}/settings", response_model=UserOut)
def patch_user_settings(user_id: int, payload: UserSettingsIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    if payload.auto_break is not None:
        user.auto_break = payload.auto_break
    if "transponder_id" in payload.model_fields_set:
        _set_transponder(db, user, payload.transponder_id)
    if payload.web_login is not None:
        next_web_login = _web_login_for(user.role, payload.web_login)
        _require_admin_for(actor, next_web_login != user.web_login, ADMIN_WEB_LOGIN_MSG)
        if next_web_login != user.web_login:
            bump_session_rev(user)
        user.web_login = next_web_login
        _require_password(user.role, user.web_login, None, bool(user.password_hash) or has_open_invite(db, user))
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="user.settings",
            entity_type="user",
            entity_id=str(user.id),
            payload=json.dumps(
                {
                    "auto_break": user.auto_break,
                    "transponder_id": user.transponder_id,
                    "web_login": user.web_login,
                }
            ),
        )
    )
    db.commit()
    db.refresh(user)
    return _user_out(user)


ALLOWED_ROLES = {"employee", "supervisor", "hr", "admin"}


@router.patch("/users/{user_id}/account", response_model=UserOut)
def patch_user_account(user_id: int, payload: UserAccountIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    user = db.scalar(select(User).options(selectinload(User.work_model)).where(User.id == user_id))
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    if payload.username is not None:
        username = normalize_username(payload.username)
        taken = db.scalar(select(User).where(func.lower(User.username) == username, User.id != user.id))
        if taken:
            raise HTTPException(409, "Benutzername vergeben")
        user.username = username
    if payload.display_name is not None:
        name = payload.display_name.strip()
        if len(name) < 2:
            raise HTTPException(400, "Name zu kurz")
        user.display_name = name
    if "email" in payload.model_fields_set:
        user.email = _set_email(payload.email)
    next_role = user.role
    if payload.role is not None:
        if payload.role not in ALLOWED_ROLES:
            raise HTTPException(400, "Ungültige Rolle")
        next_role = payload.role
    next_active = user.active if payload.active is None else payload.active
    next_web_login = _web_login_for(next_role, user.web_login)
    _require_admin_for(actor, next_role != user.role, ADMIN_ROLE_MSG)
    _require_admin_for(actor, next_active != user.active, ADMIN_ACTIVE_MSG)
    _require_admin_for(actor, bool(payload.password), ADMIN_PASSWORD_MSG)
    _ensure_not_last_admin(db, user, next_role, next_active)
    privileged = next_role != user.role or next_active != user.active or bool(payload.password)
    user.role = next_role
    user.active = next_active
    user.web_login = next_web_login
    if payload.password:
        user.password_hash = hash_password(payload.password)
        user.auth_source = "local"
    if privileged:
        bump_session_rev(user)
    if "hired_on" in payload.model_fields_set:
        user.hired_on = payload.hired_on
    if "left_on" in payload.model_fields_set:
        user.left_on = payload.left_on
    _check_employment_dates(user)
    _require_password(user.role, user.web_login, None, bool(user.password_hash) or has_open_invite(db, user))
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="user.account",
            entity_type="user",
            entity_id=str(user.id),
            payload=json.dumps(
                {
                    "username": user.username,
                    "role": user.role,
                    "active": user.active,
                    "password_set": bool(payload.password),
                    "email": user.email,
                }
            ),
        )
    )
    db.commit()
    db.refresh(user)
    if actor.id == user.id:
        write_session(request, user)
    return _user_out(user)


@router.post("/users/{user_id}/access-mail")
def send_user_access_mail(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    try:
        send_access_mail(db, user, purpose="invite")
    except MailError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="user.invite",
            entity_type="user",
            entity_id=str(user.id),
        )
    )
    db.commit()
    return {"ok": True}


@router.get("/work-models", response_model=list[WorkModelOut])
def list_models(request: Request, db: Session = Depends(get_db)):
    _actor(request, db)
    return list(db.scalars(select(WorkModel).order_by(WorkModel.name)))


@router.post("/work-models", response_model=WorkModelOut)
def create_model(payload: WorkModelIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    model = WorkModel(**payload.model_dump())
    db.add(model)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="workmodel.create",
            entity_type="work_model",
            entity_id=str(model.id),
            payload=json.dumps({"name": model.name}),
        )
    )
    db.commit()
    db.refresh(model)
    return model


@router.get("/settings", response_model=OrgSettingsOut)
def get_settings(request: Request, db: Session = Depends(get_db)):
    _actor(request, db)
    code = bundesland_of(db)
    return OrgSettingsOut(bundesland=code, bundesland_name=STATES.get(code, code), states=STATES)


@router.patch("/settings", response_model=OrgSettingsOut)
def patch_settings(payload: OrgSettingsIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor_admin(request, db)
    from app.models import OrgSettings

    code = payload.bundesland.strip().upper()
    if code not in STATES:
        raise HTTPException(400, "Unbekanntes Bundesland")
    row = db.get(OrgSettings, 1)
    if row:
        row.bundesland = code
    else:
        row = OrgSettings(id=1, bundesland=code)
        db.add(row)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="org.settings",
            entity_type="org",
            entity_id="1",
            payload=json.dumps({"bundesland": code}),
        )
    )
    db.commit()
    return OrgSettingsOut(bundesland=code, bundesland_name=STATES[code], states=STATES)


@router.get("/security-policy", response_model=SecurityPolicyOut)
def get_security_policy(request: Request, db: Session = Depends(get_db)):
    _actor(request, db)
    return SecurityPolicyOut(policies=get_policies(db), roles=list(POLICY_ROLES), values=list(POLICY_VALUES))


@router.patch("/security-policy", response_model=SecurityPolicyOut)
def patch_security_policy(payload: SecurityPolicyIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor_admin(request, db)
    for role, value in payload.policies.items():
        if role not in POLICY_ROLES or value not in POLICY_VALUES:
            raise HTTPException(400, "Ungültige Sicherheitsrichtlinie")
    policies = set_policies(db, payload.policies)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="org.security_policy",
            entity_type="org",
            entity_id="1",
            payload=json.dumps(policies),
        )
    )
    db.commit()
    return SecurityPolicyOut(policies=policies, roles=list(POLICY_ROLES), values=list(POLICY_VALUES))


@router.get("/mail-status")
def mail_status(request: Request, db: Session = Depends(get_db)):
    _actor(request, db)
    return {"ready": smtp_ready(db)}


@router.get("/smtp")
def get_smtp(request: Request, db: Session = Depends(get_db)):
    require_admin(_actor(request, db))
    return smtp_status(db)


@router.patch("/smtp")
def patch_smtp(payload: SmtpSettingsIn, request: Request, db: Session = Depends(get_db)):
    actor = require_admin(_actor(request, db))
    try:
        apply_smtp(db, payload.model_dump(exclude_unset=True))
    except MailError as exc:
        raise HTTPException(400, str(exc)) from exc
    dumped = payload.model_dump(exclude_unset=True)
    dumped.pop("password", None)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="smtp.settings",
            entity_type="org",
            entity_id="1",
            payload=json.dumps(dumped),
        )
    )
    db.commit()
    return smtp_status(db)


@router.post("/smtp/test")
def test_smtp(payload: SmtpTestIn, request: Request, db: Session = Depends(get_db)):
    actor = require_admin(_actor(request, db))
    to = payload.to or actor.email
    try:
        send_test_mail(db, to or "")
    except MailError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="smtp.test",
            entity_type="org",
            entity_id="1",
        )
    )
    db.commit()
    return {"ok": True}


@router.get("/calendar", response_model=list[CalendarOut])
def list_calendar(request: Request, db: Session = Depends(get_db), year: int = Query(..., ge=2020, le=2100)):
    _actor(request, db)
    from app.holidays import year_calendar

    return [
        CalendarOut(id=c.id, day=c.day, kind=c.kind, name=c.name, source=c.source)
        for c in year_calendar(db, year)
    ]


@router.post("/calendar", response_model=CalendarOut)
def create_calendar(payload: CalendarIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    from app.models import CalendarEntry

    existing = db.scalar(select(CalendarEntry).where(CalendarEntry.day == payload.day))
    if existing:
        existing.kind = payload.kind
        existing.name = payload.name.strip()
        existing.created_by_id = actor.id
        row = existing
    else:
        row = CalendarEntry(
            day=payload.day,
            kind=payload.kind,
            name=payload.name.strip(),
            created_by_id=actor.id,
        )
        db.add(row)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="calendar.upsert",
            entity_type="calendar",
            entity_id=str(row.id),
            payload=json.dumps({"day": payload.day.isoformat(), "kind": payload.kind, "name": payload.name.strip()}, ensure_ascii=False),
        )
    )
    db.commit()
    db.refresh(row)
    return CalendarOut(id=row.id, day=row.day, kind=row.kind, name=row.name, source="custom")


@router.delete("/calendar/{entry_id}")
def delete_calendar(entry_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    from app.models import CalendarEntry

    row = db.get(CalendarEntry, entry_id)
    if not row:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(row)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="calendar.delete",
            entity_type="calendar",
            entity_id=str(entry_id),
            payload=json.dumps({"day": row.day.isoformat()}),
        )
    )
    db.commit()
    return {"ok": True}


def _assign_out(row: WorkModelAssignment) -> WorkModelAssignOut:
    return WorkModelAssignOut(
        id=row.id,
        work_model_id=row.work_model_id,
        work_model_name=row.work_model.name if row.work_model else "",
        valid_from=row.valid_from,
        created_at=row.created_at,
    )


@router.get("/users/{user_id}/work-models", response_model=list[WorkModelAssignOut])
def list_user_models(user_id: int, request: Request, db: Session = Depends(get_db)):
    _actor(request, db)
    if not db.get(User, user_id):
        raise HTTPException(404, "Nicht gefunden")
    rows = list(
        db.scalars(
            select(WorkModelAssignment)
            .options(selectinload(WorkModelAssignment.work_model))
            .where(WorkModelAssignment.user_id == user_id)
            .order_by(WorkModelAssignment.valid_from.desc())
        )
    )
    return [_assign_out(r) for r in rows]


@router.post("/users/{user_id}/work-models", response_model=WorkModelAssignOut)
def assign_user_model(user_id: int, payload: WorkModelAssignIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    try:
        row = upsert_assignment(db, user, payload.work_model_id, payload.valid_from, actor.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="user.workmodel",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps(
                {"work_model_id": payload.work_model_id, "valid_from": payload.valid_from.isoformat()},
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    row = db.scalar(
        select(WorkModelAssignment)
        .options(selectinload(WorkModelAssignment.work_model))
        .where(WorkModelAssignment.id == row.id)
    )
    assert row
    return _assign_out(row)


@router.delete("/users/{user_id}/work-models/{assignment_id}")
def delete_user_model(user_id: int, assignment_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    row = db.get(WorkModelAssignment, assignment_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(row)
    db.flush()
    remaining = load_timeline(db, user_id)
    sync_current_model(user, remaining)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="user.workmodel.delete",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps({"id": assignment_id}),
        )
    )
    db.commit()
    return {"ok": True}


@router.get("/users/{user_id}/days")
def user_days(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    _actor(request, db)
    user = db.scalar(select(User).options(selectinload(User.work_model)).where(User.id == user_id))
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    year, mon = (int(x) for x in month.split("-"))
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    last = end - timedelta(days=1)
    accepts = {
        a.day: a
        for a in db.scalars(
            select(DayAcceptance).where(DayAcceptance.user_id == user.id, DayAcceptance.day >= start, DayAcceptance.day <= last)
        )
    }
    days = [
        _attach_accepted(d, accepts.get(date.fromisoformat(str(d["date"]))))
        for d in days_in_range(db, user, start, last)
    ]
    month_flex, total_flex = account_hours(db, user, month=month)
    return {
        "user": _user_out(user),
        "month": month,
        "days": days,
        "month_flex": month_flex,
        "total_flex": total_flex,
    }


@router.post("/users/{user_id}/corrections")
def correct(
    user_id: int,
    payload: CorrectionIn,
    request: Request,
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    if payload.punch_id:
        original = db.get(Punch, payload.punch_id)
        if not original or original.user_id != user_id:
            raise HTTPException(404, "Stempel nicht gefunden")
        original.voided_at = now_utc()
        original.voided_by_id = actor.id
        original.void_reason = payload.reason
    aware = payload.local_time
    if aware.tzinfo is None:
        from app.auth import local_tz

        aware = aware.replace(tzinfo=local_tz())
    server_time = aware.astimezone(ZoneInfo("UTC"))
    punch = Punch(
        user_id=user_id,
        kind=payload.kind,
        server_time=server_time,
        source="correction",
        client_event_id=f"corr-{actor.id}-{int(now_utc().timestamp())}-{user_id}",
        note=payload.reason,
        replaces_id=payload.punch_id,
    )
    db.add(punch)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="punch.correct",
            entity_type="punch",
            entity_id=str(punch.id),
            payload=json.dumps(
                {
                    "user_id": user_id,
                    "kind": payload.kind,
                    "reason": payload.reason,
                    "voided_id": payload.punch_id,
                    "time": server_time.isoformat(),
                }
            ),
        )
    )
    db.commit()
    return {"ok": True, "punch_id": punch.id}


@router.put("/users/{user_id}/days/{day}")
def replace_day(
    user_id: int,
    day: date,
    payload: DayReplaceIn,
    request: Request,
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    start, end = local_day_bounds(day)
    existing = list(
        db.scalars(
            select(Punch).where(
                Punch.user_id == user_id,
                Punch.server_time >= start,
                Punch.server_time < end,
                Punch.voided_at.is_(None),
            )
        )
    )
    before = [
        {"id": p.id, "kind": p.kind, "time": p.server_time.isoformat(), "source": p.source} for p in existing
    ]
    from app.auth import local_tz

    tz = local_tz()
    for p in existing:
        p.voided_at = now_utc()
        p.voided_by_id = actor.id
        p.void_reason = payload.reason
    created = []
    drafts = sorted(enumerate(payload.punches), key=lambda item: (item[1].time, item[0]))
    for i, draft in drafts:
        hour, minute = (int(x) for x in draft.time.split(":"))
        local_dt = datetime.combine(day, datetime.min.time(), tzinfo=tz).replace(hour=hour, minute=minute)
        punch = Punch(
            user_id=user_id,
            kind=draft.kind,
            server_time=local_dt.astimezone(ZoneInfo("UTC")),
            source="correction",
            client_event_id=f"corr-{user_id}-{day.isoformat()}-{i}-{int(now_utc().timestamp())}",
            note=payload.reason,
        )
        db.add(punch)
        created.append(draft.model_dump())
    db.flush()
    _clear_acceptance(db, user_id, day)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="day.replace",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps(
                {
                    "date": day.isoformat(),
                    "reason": payload.reason,
                    "before": before,
                    "after": created,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return {"ok": True, "voided": len(existing), "created": len(created)}


@router.post("/users/{user_id}/days/{day}/accept")
def accept_day(
    user_id: int,
    day: date,
    payload: DayAcceptIn,
    request: Request,
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    q_start, q_end = punches_window_for_month(day, day)
    punches = list(
        db.scalars(
            select(Punch)
            .where(Punch.user_id == user_id, Punch.server_time >= q_start, Punch.server_time < q_end)
            .order_by(Punch.server_time)
        )
    )
    absence = db.scalar(select(Absence).where(Absence.user_id == user_id, Absence.day == day))
    timeline = load_timeline(db, user_id)
    cal = calendar_map(db, day, day)
    summary = summarize_day(
        punches, day, model_for(timeline, day, user.work_model), absence=absence, auto_break=bool(user.auto_break), calendar=cal.get(day)
    )
    warning_json = json.dumps(summary.get("warnings") or [], ensure_ascii=False)
    existing = db.scalar(select(DayAcceptance).where(DayAcceptance.user_id == user_id, DayAcceptance.day == day))
    if existing:
        existing.reason = payload.reason.strip()
        existing.warnings = warning_json
        existing.accepted_by_id = actor.id
        existing.accepted_at = now_utc()
        row = existing
    else:
        row = DayAcceptance(
            user_id=user_id,
            day=day,
            reason=payload.reason.strip(),
            warnings=warning_json,
            accepted_by_id=actor.id,
            accepted_at=now_utc(),
        )
        db.add(row)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="day.accept",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps({"date": day.isoformat(), "reason": payload.reason.strip()}, ensure_ascii=False),
        )
    )
    db.commit()
    return {"ok": True, "id": row.id}


@router.delete("/users/{user_id}/days/{day}/accept")
def revoke_accept(user_id: int, day: date, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not db.get(User, user_id):
        raise HTTPException(404, "Nicht gefunden")
    _clear_acceptance(db, user_id, day)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="day.accept.revoke",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps({"date": day.isoformat()}),
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/absences")
def create_absences(user_id: int, payload: AbsenceRangeIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not db.get(User, user_id):
        raise HTTPException(404, "Nicht gefunden")
    if payload.end < payload.start:
        raise HTTPException(400, "Ende liegt vor dem Beginn")
    if (payload.end - payload.start).days > 90:
        raise HTTPException(400, "Maximal 90 Tage am Stück")
    created = 0
    cur = payload.start
    while cur <= payload.end:
        row = db.scalar(select(Absence).where(Absence.user_id == user_id, Absence.day == cur))
        if row:
            row.kind = payload.kind
            row.note = payload.note
        else:
            db.add(
                Absence(
                    user_id=user_id,
                    day=cur,
                    kind=payload.kind,
                    note=payload.note,
                    created_by_id=actor.id,
                )
            )
            created += 1
        _clear_acceptance(db, user_id, cur)
        cur += timedelta(days=1)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="absence.create",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps(
                {
                    "kind": payload.kind,
                    "start": payload.start.isoformat(),
                    "end": payload.end.isoformat(),
                    "note": payload.note,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return {"ok": True, "created": created}


@router.delete("/users/{user_id}/absences/{day}")
def delete_absence(user_id: int, day: date, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    row = db.scalar(select(Absence).where(Absence.user_id == user_id, Absence.day == day))
    if not row:
        raise HTTPException(404, "Keine Abwesenheit")
    kind = row.kind
    db.delete(row)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="absence.delete",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps({"date": day.isoformat(), "kind": kind}),
        )
    )
    db.commit()
    return {"ok": True}


ISSUE_KEYS = ("missing_day", "checkout_missing", "break_short", "break_short_9h", "break_long", "over_10h")


@router.get("/balances")
def balances(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    _actor(request, db)
    year, mon = (int(x) for x in month.split("-"))
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    last = end - timedelta(days=1)
    q_start, q_end = punches_window_for_month(start, last)
    users = list(db.scalars(select(User).options(selectinload(User.work_model)).order_by(User.display_name)))
    timelines = load_timelines(db, [u.id for u in users])
    cal = calendar_map(db, start, last)
    today = as_local(now_utc()).date()
    people = []
    for user in users:
        punches = list(
            db.scalars(
                select(Punch)
                .where(Punch.user_id == user.id, Punch.server_time >= q_start, Punch.server_time < q_end)
                .order_by(Punch.server_time)
            )
        )
        absences = {
            a.day: a
            for a in db.scalars(select(Absence).where(Absence.user_id == user.id, Absence.day >= start, Absence.day <= last))
        }
        work = soll = delta = 0.0
        cur = start
        while cur < end:
            summary = summarize_user_day(
                user,
                punches,
                cur,
                timelines.get(user.id, []),
                absence=absences.get(cur),
                calendar=cal.get(cur),
            )
            if cur <= today:
                work += float(summary["work_hours"] or 0)
                soll += float(summary["soll_hours"] or 0)
                delta += float(summary["delta_hours"] or 0)
            cur += timedelta(days=1)
        _month_flex, total_flex = account_hours(db, user, month=month)
        people.append(
            {
                "user_id": user.id,
                "work_hours": round(work, 1),
                "soll_hours": round(soll, 1),
                "delta_hours": round(delta, 1),
                "total_delta_hours": total_flex,
            }
        )
    return {"month": month, "people": people}


@router.get("/plausibility")
def plausibility(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    _actor(request, db)
    year, mon = (int(x) for x in month.split("-"))
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    last = end - timedelta(days=1)
    q_start, q_end = punches_window_for_month(start, last)
    users = list(
        db.scalars(
            select(User)
            .options(selectinload(User.work_model))
            .where(User.active.is_(True), User.role.in_(("employee", "supervisor")))
            .order_by(User.display_name)
        )
    )
    timelines = load_timelines(db, [u.id for u in users])
    cal = calendar_map(db, start, last)
    rows = []
    for user in users:
        punches = list(
            db.scalars(
                select(Punch)
                .where(Punch.user_id == user.id, Punch.server_time >= q_start, Punch.server_time < q_end)
                .order_by(Punch.server_time)
            )
        )
        absences = {
            a.day: a
            for a in db.scalars(select(Absence).where(Absence.user_id == user.id, Absence.day >= start, Absence.day <= last))
        }
        accepts = {
            a.day: a
            for a in db.scalars(
                select(DayAcceptance).where(DayAcceptance.user_id == user.id, DayAcceptance.day >= start, DayAcceptance.day <= last)
            )
        }
        counts = {k: 0 for k in ISSUE_KEYS}
        flagged: list[dict] = []
        cur = start
        while cur < end:
            if cur in accepts:
                cur += timedelta(days=1)
                continue
            summary = summarize_user_day(
                user,
                punches,
                cur,
                timelines.get(user.id, []),
                absence=absences.get(cur),
                calendar=cal.get(cur),
            )
            issues = [w for w in summary["warnings"] if w in counts]
            if issues:
                for w in issues:
                    counts[w] += 1
                flagged.append({"date": summary["date"], "warnings": issues})
            cur += timedelta(days=1)
        total = sum(counts.values())
        if total == 0:
            continue
        rows.append(
            {
                "user": UserOut.model_validate(user),
                "model_name": user.work_model.name if user.work_model else None,
                "issue_count": total,
                "days_with_issues": len(flagged),
                "counts": counts,
                "days": flagged,
            }
        )
    rows.sort(key=lambda r: r["issue_count"], reverse=True)
    return {"month": month, "people": rows}


@router.get("/audit")
def audit(request: Request, db: Session = Depends(get_db), limit: int = 100):
    _actor(request, db)
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.at.desc()).limit(min(limit, 500))).all()
    return [
        {
            "id": r.id,
            "at": r.at,
            "actor_id": r.actor_id,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "payload": r.payload,
        }
        for r in rows
    ]


@router.get("/export.csv")
def export_csv(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    user_id: int | None = None,
):
    _actor(request, db)
    q = select(User).options(selectinload(User.work_model)).order_by(User.display_name)
    if user_id:
        q = q.where(User.id == user_id)
    users = list(db.scalars(q))
    timelines = load_timelines(db, [u.id for u in users])
    year, mon = (int(x) for x in month.split("-"))
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    last = end - timedelta(days=1)
    cal = calendar_map(db, start, last)
    q_start, q_end = punches_window_for_month(start, last)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Name", "Datum", "Kommen", "Gehen", "Ist", "Pause", "Soll", "Konto", "Abwesenheit", "Hinweise"])
    for user in users:
        punches = list(
            db.scalars(
                select(Punch)
                .where(Punch.user_id == user.id, Punch.server_time >= q_start, Punch.server_time < q_end)
                .order_by(Punch.server_time)
            )
        )
        absences = {
            a.day: a
            for a in db.scalars(
                select(Absence).where(Absence.user_id == user.id, Absence.day >= start, Absence.day <= last)
            )
        }
        cur = start
        while cur < end:
            day = summarize_user_day(
                user,
                punches,
                cur,
                timelines.get(user.id, []),
                absence=absences.get(cur),
                calendar=cal.get(cur),
            )
            if day["work_hours"] or day["first_in"] or day["warnings"] or day["absence"] or day.get("calendar"):
                day_cal = day.get("calendar") or {}
                writer.writerow(
                    [
                        user.display_name,
                        day["date"],
                        day["first_in"] or "",
                        day["last_out"] or "",
                        str(day["work_hours"]).replace(".", ","),
                        str(day["break_hours"]).replace(".", ","),
                        str(day["soll_hours"]).replace(".", ","),
                        str(day["delta_hours"]).replace(".", ","),
                        (day["absence"] or {}).get("kind", "") if day["absence"] else day_cal.get("name", ""),
                        ",".join(_warn_de(w) for w in day["warnings"]),
                    ]
                )
            cur += timedelta(days=1)
    payload = "\ufeff" + buf.getvalue()
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="zeiten-{month}.csv"'},
    )
