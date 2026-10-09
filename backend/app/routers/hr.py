from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.auth import HR_ROLES, as_local, bump_session_rev, current_user, local_day_bounds, normalize_username, now_utc, require_admin, require_hr, require_hr_full, write_session
from app.balance import account_hours, days_in_range, format_hm, load_day_models, summarize_user_day
from app.closing_job import job_status, start_close, start_recalculate
from app.closings import (
    any_closing,
    drop_closings_before,
    earliest_per_user,
    listed_total,
    month_is_closed,
    recalculate_pairs,
    require_open,
    users_for_day,
)
from app.datafox import normalize_badge
from app.database import get_db
from app.names import compose_display_name, name_sort_key, person_sort_key, split_person_name
from app.accounts import vacation_days
from app.models import (
    Absence,
    AccountEntry,
    AuditEvent,
    CalendarEntry,
    DayAcceptance,
    DayModel,
    Department,
    MonthClosing,
    MailToken,
    Punch,
    TotpBackupCode,
    User,
    WebAuthnCredential,
    WorkModel,
    WorkModelAssignment,
)
from app.schemas import (
    AbsenceRangeIn,
    AccountEntryIn,
    CalendarIn,
    CalendarOut,
    ClosingMonthIn,
    CorrectionIn,
    DayAcceptIn,
    DayModelIn,
    DayReplaceIn,
    DepartmentIn,
    DepartmentOut,
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
from app.reports import safe_csv_cell
from app.timecalc import punches_window_for_month
from app.workmodels import (
    CLOSED_NOTICE,
    closed_month_count,
    ensure_initial_assignment,
    freeze_rules,
    load_frozen_map,
    load_timeline,
    load_timelines,
    model_for,
    normalize_break_rules,
    normalize_fixed_breaks,
    normalize_corridor,
    normalize_shifts,
    stored_break_rules,
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
    if code.startswith("break_short:") and code.count(":") == 2:
        _, minutes, hours = code.split(":")
        if minutes.isdigit():
            return f"Pause unter {minutes} Min. (ab {hours.replace('.', ',')} Std.)"
    return _WARN_DE.get(code, code)


def _actor(request: Request, db: Session) -> User:
    return require_hr(current_user(request, db))


def _actor_full(request: Request, db: Session) -> User:
    return require_hr_full(current_user(request, db))


ALLOWED_ROLES = {"employee", "supervisor", "hr", "admin"}


def _require_known_role(role: str) -> None:
    if role not in ALLOWED_ROLES:
        raise HTTPException(400, "Ungültige Rolle")


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


def _apply_name(user: User, raw: str) -> None:
    first, last = split_person_name(raw)
    user.first_name = first[:80]
    user.last_name = last[:120]
    user.display_name = compose_display_name(user.first_name, user.last_name)[:160]


def _apply_name_parts(user: User, first: str, last: str) -> None:
    user.first_name = " ".join((first or "").split())[:80]
    user.last_name = " ".join((last or "").split())[:120]
    user.display_name = compose_display_name(user.first_name, user.last_name)[:160]


def _by_name(user: User) -> str:
    return person_sort_key(user.first_name, user.last_name, user.display_name)


def _user_with_rels():
    return select(User).options(selectinload(User.work_model), selectinload(User.department))


def _user_out(user: User, *, redact_pii: bool = False) -> UserOut:
    out = UserOut.model_validate(user)
    update: dict = {
        "work_model_name": user.work_model.name if user.work_model else None,
        "department_name": user.department.name if user.department else None,
    }
    if redact_pii:
        update.update({"email": None, "birthday": None, "transponder_id": None})
    return out.model_copy(update=update)


def _department_by_id(db: Session, department_id: int | None) -> Department | None:
    if department_id is None:
        return None
    dept = db.get(Department, department_id)
    if not dept:
        raise HTTPException(400, "Abteilung nicht gefunden")
    return dept


def _set_department(db: Session, user: User, department_id: int | None) -> None:
    dept = _department_by_id(db, department_id)
    user.department_id = dept.id if dept is not None else None
    user.department = dept


def _norm_dept_name(name: str) -> str:
    cleaned = " ".join(name.split()).strip()
    if not cleaned:
        raise HTTPException(400, "Name der Abteilung fehlt")
    return cleaned


def _dept_name_taken(db: Session, name: str, exclude_id: int | None = None) -> bool:
    q = select(Department).where(func.lower(Department.name) == name.lower())
    if exclude_id is not None:
        q = q.where(Department.id != exclude_id)
    return db.scalar(q) is not None


def _dept_out(db: Session, dept: Department) -> DepartmentOut:
    count = db.scalar(select(func.count(User.id)).where(User.department_id == dept.id)) or 0
    return DepartmentOut(id=dept.id, name=dept.name, user_count=int(count))


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
    actor = _actor(request, db)
    users = sorted(db.scalars(_user_with_rels()), key=_by_name)
    counts = passkey_counts(db, [u.id for u in users])
    redact = actor.role == "supervisor"
    return [_user_out(u, redact_pii=redact).model_copy(update={"passkey_count": counts.get(u.id, 0)}) for u in users]


@router.post("/users", response_model=UserCreateOut)
def create_user(payload: UserWrite, request: Request, db: Session = Depends(get_db)):
    actor = _actor_full(request, db)
    _require_known_role(payload.role)
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
    dept = _department_by_id(db, payload.department_id)
    user = User(
        username=username,
        display_name="",
        email=email,
        role=payload.role,
        active=payload.active,
        work_model_id=payload.work_model_id,
        department_id=dept.id if dept is not None else None,
        auth_source="local",
        password_hash=hash_password(payload.password) if payload.password else None,
        auto_break=payload.auto_break,
        web_login=web_login,
        hired_on=payload.hired_on or as_local(now_utc()).date(),
        left_on=payload.left_on,
        birthday=payload.birthday,
        vacation_days_year=payload.vacation_days_year,
    )
    if payload.first_name.strip() or payload.last_name.strip():
        _apply_name_parts(user, payload.first_name, payload.last_name)
    else:
        _apply_name(user, payload.display_name)
    if len(user.display_name) < 2:
        raise HTTPException(400, "Name zu kurz")
    user.department = dept
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
    actor = _actor_full(request, db)
    _require_known_role(payload.role)
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
    if payload.first_name.strip() or payload.last_name.strip():
        _apply_name_parts(user, payload.first_name, payload.last_name)
    else:
        _apply_name(user, payload.display_name)
    if len(user.display_name) < 2:
        raise HTTPException(400, "Name zu kurz")
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
    if "department_id" in payload.model_fields_set:
        _set_department(db, user, payload.department_id)
    if "auto_break" in payload.model_fields_set:
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
    if "birthday" in payload.model_fields_set:
        user.birthday = payload.birthday
    if "vacation_days_year" in payload.model_fields_set:
        user.vacation_days_year = payload.vacation_days_year
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
    actor = _actor_full(request, db)
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


@router.patch("/users/{user_id}/account", response_model=UserOut)
def patch_user_account(user_id: int, payload: UserAccountIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor_full(request, db)
    user = db.scalar(_user_with_rels().where(User.id == user_id))
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    if payload.username is not None:
        username = normalize_username(payload.username)
        taken = db.scalar(select(User).where(func.lower(User.username) == username, User.id != user.id))
        if taken:
            raise HTTPException(409, "Benutzername vergeben")
        user.username = username
    name_parts = "first_name" in payload.model_fields_set or "last_name" in payload.model_fields_set
    if name_parts or payload.display_name is not None:
        if name_parts:
            _apply_name_parts(
                user,
                payload.first_name if payload.first_name is not None else user.first_name,
                payload.last_name if payload.last_name is not None else user.last_name,
            )
        else:
            _apply_name(user, payload.display_name or "")
        if len(user.display_name) < 2:
            raise HTTPException(400, "Name zu kurz")
    if "email" in payload.model_fields_set:
        user.email = _set_email(payload.email)
    next_role = user.role
    if payload.role is not None:
        _require_known_role(payload.role)
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
    flex_flag_changed = (
        "skip_flex_on_close" in payload.model_fields_set
        and bool(payload.skip_flex_on_close) != bool(user.skip_flex_on_close)
    )
    opening_changed = (
        ("opening_balance_hours" in payload.model_fields_set and payload.opening_balance_hours != user.opening_balance_hours)
        or ("opening_balance_on" in payload.model_fields_set and payload.opening_balance_on != user.opening_balance_on)
        or ("hired_on" in payload.model_fields_set and payload.hired_on != user.hired_on)
        or flex_flag_changed
    )
    recalc: list[tuple[int, int, int]] = []
    if opening_changed:
        earliest = db.scalar(
            select(MonthClosing)
            .where(MonthClosing.user_id == user.id)
            .order_by(MonthClosing.year, MonthClosing.month)
        )
        if earliest is not None:
            recalc = require_open(db, [(user.id, date(earliest.year, earliest.month, 1))], payload.confirm_closed)
    if "hired_on" in payload.model_fields_set:
        user.hired_on = payload.hired_on
    if "opening_balance_hours" in payload.model_fields_set and payload.opening_balance_hours is not None:
        user.opening_balance_hours = float(payload.opening_balance_hours)
    if "opening_balance_on" in payload.model_fields_set:
        user.opening_balance_on = payload.opening_balance_on
    if "flex_cap_hours" in payload.model_fields_set:
        user.flex_cap_hours = None if payload.flex_cap_hours is None else float(payload.flex_cap_hours)
    if "skip_flex_on_close" in payload.model_fields_set and payload.skip_flex_on_close is not None:
        user.skip_flex_on_close = bool(payload.skip_flex_on_close)
    if "left_on" in payload.model_fields_set:
        user.left_on = payload.left_on
    if "birthday" in payload.model_fields_set:
        user.birthday = payload.birthday
    if "vacation_days_year" in payload.model_fields_set:
        user.vacation_days_year = payload.vacation_days_year
    if "department_id" in payload.model_fields_set:
        _set_department(db, user, payload.department_id)
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
                    "opening_balance_hours": user.opening_balance_hours,
                    "opening_balance_on": user.opening_balance_on.isoformat() if user.opening_balance_on else None,
                    "flex_cap_hours": user.flex_cap_hours,
                    "skip_flex_on_close": user.skip_flex_on_close,
                }
            ),
        )
    )
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
    db.commit()
    db.refresh(user)
    if actor.id == user.id:
        write_session(request, user)
    return _user_out(user)


def _drop_user_rows(db: Session, user: User, actor: User) -> None:
    uid = user.id
    punch_ids = list(db.scalars(select(Punch.id).where(Punch.user_id == uid)))
    if punch_ids:
        db.execute(update(Punch).where(Punch.replaces_id.in_(punch_ids)).values(replaces_id=None))
    db.execute(update(Punch).where(Punch.voided_by_id == uid).values(voided_by_id=None))
    db.execute(update(Punch).where(Punch.user_id == uid).values(replaces_id=None, voided_by_id=None))
    db.execute(delete(Punch).where(Punch.user_id == uid))
    db.execute(update(Absence).where(Absence.created_by_id == uid).values(created_by_id=actor.id))
    db.execute(delete(Absence).where(Absence.user_id == uid))
    db.execute(update(DayAcceptance).where(DayAcceptance.accepted_by_id == uid).values(accepted_by_id=actor.id))
    db.execute(delete(DayAcceptance).where(DayAcceptance.user_id == uid))
    db.execute(update(MonthClosing).where(MonthClosing.closed_by_id == uid).values(closed_by_id=None))
    db.execute(delete(MonthClosing).where(MonthClosing.user_id == uid))
    db.execute(update(AccountEntry).where(AccountEntry.created_by_id == uid).values(created_by_id=actor.id))
    db.execute(delete(AccountEntry).where(AccountEntry.user_id == uid))
    db.execute(update(WorkModelAssignment).where(WorkModelAssignment.created_by_id == uid).values(created_by_id=actor.id))
    db.execute(delete(WorkModelAssignment).where(WorkModelAssignment.user_id == uid))
    db.execute(update(CalendarEntry).where(CalendarEntry.created_by_id == uid).values(created_by_id=actor.id))
    db.execute(delete(MailToken).where(MailToken.user_id == uid))
    db.execute(delete(TotpBackupCode).where(TotpBackupCode.user_id == uid))
    db.execute(delete(WebAuthnCredential).where(WebAuthnCredential.user_id == uid))
    db.execute(update(AuditEvent).where(AuditEvent.actor_id == uid).values(actor_id=None))


@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor_admin(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    if actor.id == user.id:
        raise HTTPException(400, "Das eigene Konto kann hier nicht gelöscht werden")
    if user.role == "admin" and _active_admin_count(db) <= 1 and user.active:
        raise HTTPException(400, "Der letzte Administrator kann nicht gelöscht werden")
    name = user.display_name
    username = user.username
    _drop_user_rows(db, user, actor)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="user.delete",
            entity_type="user",
            entity_id=str(user.id),
            payload=json.dumps({"username": username, "display_name": name}),
        )
    )
    db.delete(user)
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/access-mail")
def send_user_access_mail(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor_full(request, db)
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


def _model_out(db: Session, model: WorkModel, notice: str | None = None) -> WorkModelOut:
    try:
        corridor = normalize_corridor(json.loads(model.booking_corridor or "{}"))
    except (json.JSONDecodeError, ValueError):
        corridor = {}
    try:
        shifts = normalize_shifts(json.loads(model.shifts or "[]"))
    except (json.JSONDecodeError, ValueError):
        shifts = []
    rules = stored_break_rules(model.break_rules)
    try:
        fixed = normalize_fixed_breaks(json.loads(model.fixed_breaks or "{}"))
    except (json.JSONDecodeError, ValueError):
        fixed = {}
    closed = closed_month_count(db, model.id)
    return WorkModelOut(
        id=model.id,
        name=model.name,
        kind=model.kind,
        hours_mon=model.hours_mon,
        hours_tue=model.hours_tue,
        hours_wed=model.hours_wed,
        hours_thu=model.hours_thu,
        hours_fri=model.hours_fri,
        hours_sat=model.hours_sat,
        hours_sun=model.hours_sun,
        round_start_before=model.round_start_before,
        round_start_after=model.round_start_after,
        round_end_before=model.round_end_before,
        round_end_after=model.round_end_after,
        round_first_threshold=model.round_first_threshold,
        round_first_step=model.round_first_step,
        round_last_threshold=model.round_last_threshold,
        round_last_step=model.round_last_step,
        booking_corridor=corridor,
        shifts=shifts,
        break_rules=rules,
        break_mode="fixed" if model.break_mode == "fixed" else "threshold",
        fixed_breaks=fixed,
        closed_months=closed,
        notice=notice,
    )


def _apply_model(model: WorkModel, payload: WorkModelIn) -> None:
    try:
        corridor = normalize_corridor(payload.booking_corridor)
        shifts = normalize_shifts(payload.shifts)
        rules = normalize_break_rules(payload.break_rules)
        fixed = normalize_fixed_breaks(payload.fixed_breaks)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if payload.break_mode not in {"threshold", "fixed"}:
        raise HTTPException(400, "Unbekannte Pausenregel")
    data = payload.model_dump(exclude={"booking_corridor", "shifts", "break_rules", "fixed_breaks"})
    for key, value in data.items():
        setattr(model, key, value)
    model.booking_corridor = json.dumps(corridor)
    model.shifts = json.dumps(shifts)
    model.break_rules = json.dumps(rules)
    model.fixed_breaks = json.dumps(fixed)


@router.get("/work-models", response_model=list[WorkModelOut])
def list_models(request: Request, db: Session = Depends(get_db)):
    _actor(request, db)
    return [_model_out(db, model) for model in db.scalars(select(WorkModel).order_by(WorkModel.name))]


@router.post("/work-models", response_model=WorkModelOut)
def create_model(payload: WorkModelIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor_full(request, db)
    model = WorkModel(name=payload.name, kind=payload.kind)
    _apply_model(model, payload)
    db.add(model)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="workmodel.create",
            entity_type="work_model",
            entity_id=str(model.id),
        )
    )
    db.commit()
    db.refresh(model)
    return _model_out(db, model)


@router.patch("/work-models/{model_id}", response_model=WorkModelOut)
def update_model(model_id: int, payload: WorkModelIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor_full(request, db)
    model = db.get(WorkModel, model_id)
    if model is None:
        raise HTTPException(404, "Nicht gefunden")
    closed = closed_month_count(db, model.id)
    if closed:
        freeze_rules(db, model)
    _apply_model(model, payload)
    notice = CLOSED_NOTICE if closed else None
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="workmodel.update",
            entity_type="work_model",
            entity_id=str(model.id),
            payload=json.dumps({"closed_months": closed}, ensure_ascii=False),
        )
    )
    db.commit()
    db.refresh(model)
    return _model_out(db, model, notice=notice)


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(request: Request, db: Session = Depends(get_db)):
    _actor(request, db)
    depts = list(db.scalars(select(Department).order_by(Department.name)))
    return [_dept_out(db, dept) for dept in depts]


@router.post("/departments", response_model=DepartmentOut)
def create_department(payload: DepartmentIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor_full(request, db)
    name = _norm_dept_name(payload.name)
    if _dept_name_taken(db, name):
        raise HTTPException(409, "Abteilung gibt es schon")
    dept = Department(name=name)
    db.add(dept)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="department.create",
            entity_type="department",
            entity_id=str(dept.id),
            payload=json.dumps({"name": dept.name}),
        )
    )
    db.commit()
    db.refresh(dept)
    return _dept_out(db, dept)


@router.patch("/departments/{department_id}", response_model=DepartmentOut)
def patch_department(department_id: int, payload: DepartmentIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor_full(request, db)
    dept = db.get(Department, department_id)
    if not dept:
        raise HTTPException(404, "Nicht gefunden")
    name = _norm_dept_name(payload.name)
    if _dept_name_taken(db, name, exclude_id=dept.id):
        raise HTTPException(409, "Abteilung gibt es schon")
    dept.name = name
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="department.update",
            entity_type="department",
            entity_id=str(dept.id),
            payload=json.dumps({"name": dept.name}),
        )
    )
    db.commit()
    db.refresh(dept)
    return _dept_out(db, dept)


@router.delete("/departments/{department_id}")
def delete_department(department_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor_full(request, db)
    dept = db.get(Department, department_id)
    if not dept:
        raise HTTPException(404, "Nicht gefunden")
    used = db.scalar(select(func.count(User.id)).where(User.department_id == dept.id)) or 0
    if used:
        raise HTTPException(409, "Abteilung ist noch zugeordnet")
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="department.delete",
            entity_type="department",
            entity_id=str(dept.id),
            payload=json.dumps({"name": dept.name}),
        )
    )
    db.delete(dept)
    db.commit()
    return {"ok": True}


def _settings_out(db: Session, code: str) -> OrgSettingsOut:
    from app.models import OrgSettings

    row = db.get(OrgSettings, 1)
    return OrgSettingsOut(
        bundesland=code,
        bundesland_name=STATES.get(code, code),
        states=STATES,
        ledger_from=row.ledger_from if row else None,
    )


@router.get("/settings", response_model=OrgSettingsOut)
def get_settings(request: Request, db: Session = Depends(get_db)):
    _actor(request, db)
    return _settings_out(db, bundesland_of(db))


@router.patch("/settings", response_model=OrgSettingsOut)
def patch_settings(payload: OrgSettingsIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor_admin(request, db)
    from app.models import OrgSettings

    code = payload.bundesland.strip().upper()
    if code not in STATES:
        raise HTTPException(400, "Unbekanntes Bundesland")
    current = bundesland_of(db)
    row = db.get(OrgSettings, 1)
    if row is None:
        row = OrgSettings(id=1, bundesland=code)
        db.add(row)
    ledger_changed = "ledger_from" in payload.model_fields_set and payload.ledger_from != row.ledger_from
    bundesland_changed = code != current
    recalc: list[tuple[int, int, int]] = []
    if (bundesland_changed or ledger_changed) and any_closing(db):
        recalc = earliest_per_user(db)
        if not payload.confirm_closed and recalc:
            year, month = min((item[1], item[2]) for item in recalc)
            from app.closings import closed_detail

            raise HTTPException(status_code=409, detail=closed_detail(year, month))
    row.bundesland = code
    if ledger_changed:
        row.ledger_from = payload.ledger_from
        if payload.ledger_from is not None:
            drop_closings_before(db, payload.ledger_from.year, payload.ledger_from.month)
            db.flush()
            recalc = [
                (user_id, payload.ledger_from.year, payload.ledger_from.month)
                for user_id in db.scalars(
                    select(MonthClosing.user_id)
                    .where(
                        or_(
                            MonthClosing.year > payload.ledger_from.year,
                            and_(
                                MonthClosing.year == payload.ledger_from.year,
                                MonthClosing.month >= payload.ledger_from.month,
                            ),
                        )
                    )
                    .distinct()
                ).all()
            ]
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="org.settings",
            entity_type="org",
            entity_id="1",
            payload=json.dumps(
                {
                    "bundesland": code,
                    "ledger_from": row.ledger_from.isoformat() if row.ledger_from else None,
                }
            ),
        )
    )
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
    db.commit()
    return _settings_out(db, code)


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
    actor = _actor_full(request, db)
    from app.models import CalendarEntry

    recalc = require_open(db, users_for_day(db, payload.day), payload.confirm_closed)
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
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
    db.commit()
    db.refresh(row)
    return CalendarOut(id=row.id, day=row.day, kind=row.kind, name=row.name, source="custom")


@router.delete("/calendar/{entry_id}")
def delete_calendar(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    confirm_closed: bool = Query(False),
):
    actor = _actor_full(request, db)
    from app.models import CalendarEntry

    row = db.get(CalendarEntry, entry_id)
    if not row:
        raise HTTPException(404, "Nicht gefunden")
    recalc = require_open(db, users_for_day(db, row.day), confirm_closed)
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
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
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
    actor = _actor_full(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    recalc = require_open(db, [(user_id, payload.valid_from)], payload.confirm_closed)
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
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
    db.commit()
    row = db.scalar(
        select(WorkModelAssignment)
        .options(selectinload(WorkModelAssignment.work_model))
        .where(WorkModelAssignment.id == row.id)
    )
    assert row
    return _assign_out(row)


@router.delete("/users/{user_id}/work-models/{assignment_id}")
def delete_user_model(
    user_id: int,
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    confirm_closed: bool = Query(False),
):
    actor = _actor_full(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    row = db.get(WorkModelAssignment, assignment_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, "Nicht gefunden")
    recalc = require_open(db, [(user_id, row.valid_from)], confirm_closed)
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
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
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
    user = db.scalar(_user_with_rels().where(User.id == user_id))
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
        "closed": month_is_closed(db, user.id, start),
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
    original = None
    if payload.punch_id:
        original = db.get(Punch, payload.punch_id)
        if not original or original.user_id != user_id:
            raise HTTPException(404, "Stempel nicht gefunden")
    aware = payload.local_time
    if aware.tzinfo is None:
        from app.auth import local_tz

        aware = aware.replace(tzinfo=local_tz())
    touched = [as_local(aware).date()]
    if original is not None:
        touched.append(as_local(original.server_time).date())
    recalc = require_open(db, [(user_id, day) for day in touched], payload.confirm_closed)
    if original is not None:
        original.voided_at = now_utc()
        original.voided_by_id = actor.id
        original.void_reason = payload.reason
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
    recalculate_pairs(db, recalc, actor.id)
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
    recalc = require_open(db, [(user_id, day)], payload.confirm_closed)
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
            client_event_id=f"corr-{user_id}-{day.isoformat()}-{i}-{now_utc().timestamp()}",
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
    recalculate_pairs(db, recalc, actor.id)
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
    day_model = db.scalar(
        select(DayModel).options(selectinload(DayModel.work_model)).where(DayModel.user_id == user_id, DayModel.day == day)
    )
    timeline = load_timeline(db, user_id)
    cal = calendar_map(db, day, day)
    frozen = load_frozen_map(db, [user_id]).get((user_id, day.year, day.month))
    summary = summarize_user_day(
        user,
        punches,
        day,
        timeline,
        absence=absence,
        calendar=cal.get(day),
        frozen=frozen,
        model_override=day_model.work_model if day_model else None,
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


@router.put("/users/{user_id}/days/{day}/model")
def set_day_model(
    user_id: int,
    day: date,
    payload: DayModelIn,
    request: Request,
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    chosen = db.get(WorkModel, payload.work_model_id)
    if not chosen:
        raise HTTPException(400, "Arbeitszeitmodell nicht gefunden")
    standing = model_for(load_timeline(db, user_id), day, user.work_model)
    recalc = require_open(db, [(user_id, day)], payload.confirm_closed)
    row = db.scalar(select(DayModel).where(DayModel.user_id == user_id, DayModel.day == day))
    if standing is not None and standing.id == chosen.id:
        if row:
            db.delete(row)
        stored_id = None
        stored_name = None
    elif row:
        row.work_model_id = chosen.id
        row.created_by_id = actor.id
        stored_id = chosen.id
        stored_name = chosen.name
    else:
        db.add(DayModel(user_id=user_id, day=day, work_model_id=chosen.id, created_by_id=actor.id))
        stored_id = chosen.id
        stored_name = chosen.name
    _clear_acceptance(db, user_id, day)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="day.model",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps(
                {"date": day.isoformat(), "work_model_id": stored_id, "work_model_name": stored_name},
                ensure_ascii=False,
            ),
        )
    )
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
    db.commit()
    return {"ok": True, "work_model_id": stored_id, "work_model_name": stored_name}


@router.delete("/users/{user_id}/days/{day}/model")
def clear_day_model(
    user_id: int,
    day: date,
    request: Request,
    db: Session = Depends(get_db),
    confirm_closed: bool = Query(False),
):
    actor = _actor(request, db)
    row = db.scalar(select(DayModel).where(DayModel.user_id == user_id, DayModel.day == day))
    if not row:
        raise HTTPException(404, "Kein Tagesmodell")
    recalc = require_open(db, [(user_id, day)], confirm_closed)
    db.delete(row)
    _clear_acceptance(db, user_id, day)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="day.model.clear",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps({"date": day.isoformat()}),
        )
    )
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
    db.commit()
    return {"ok": True}


def _entry_out(row: AccountEntry) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "day": row.day.isoformat(),
        "amount": row.amount,
        "reason": row.reason,
    }


@router.get("/users/{user_id}/ledger")
def user_ledger(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    year: int = Query(..., ge=2000, le=2100),
):
    _actor(request, db)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Nicht gefunden")
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    entries = list(
        db.scalars(
            select(AccountEntry)
            .where(AccountEntry.user_id == user_id, AccountEntry.day >= start, AccountEntry.day <= end)
            .order_by(AccountEntry.day, AccountEntry.id)
        )
    )
    absences = list(
        db.scalars(
            select(Absence)
            .where(Absence.user_id == user_id, Absence.kind == "vacation", Absence.day >= start, Absence.day <= end)
            .order_by(Absence.day)
        )
    )
    time_rows = [_entry_out(row) for row in entries if row.kind == "time"]
    vacation_rows = [_entry_out(row) for row in entries if row.kind == "vacation"]
    allowance = user.vacation_days_year
    taken = len(absences)
    booked = vacation_days(db, user.id, start, end)
    remaining = None if allowance is None else float(allowance) - taken + booked
    return {
        "year": year,
        "opening_balance_hours": user.opening_balance_hours,
        "opening_balance_on": user.opening_balance_on.isoformat() if user.opening_balance_on else None,
        "time_entries": time_rows,
        "vacation_allowance": allowance,
        "vacation_days": [{"day": row.day.isoformat(), "note": row.note or ""} for row in absences],
        "vacation_entries": vacation_rows,
        "vacation_remaining": remaining,
    }


@router.post("/users/{user_id}/ledger")
def create_ledger_entry(user_id: int, payload: AccountEntryIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Nicht gefunden")
    if payload.amount == 0:
        raise HTTPException(400, "Betrag ist 0")
    recalc = require_open(db, [(user_id, payload.day)], payload.confirm_closed)
    row = AccountEntry(
        user_id=user_id,
        kind=payload.kind,
        day=payload.day,
        amount=float(payload.amount),
        reason=payload.reason.strip(),
        created_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="account.entry",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps(
                {"id": row.id, "kind": row.kind, "day": row.day.isoformat(), "amount": row.amount, "reason": row.reason},
                ensure_ascii=False,
            ),
        )
    )
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
    db.commit()
    return _entry_out(row)


@router.delete("/users/{user_id}/ledger/{entry_id}")
def delete_ledger_entry(
    user_id: int,
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    confirm_closed: bool = Query(False),
):
    actor = _actor(request, db)
    row = db.scalar(select(AccountEntry).where(AccountEntry.id == entry_id, AccountEntry.user_id == user_id))
    if row is None:
        raise HTTPException(404, "Nicht gefunden")
    recalc = require_open(db, [(user_id, row.day)], confirm_closed)
    db.delete(row)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="account.entry.delete",
            entity_type="user",
            entity_id=str(user_id),
            payload=json.dumps({"id": entry_id, "day": row.day.isoformat()}, ensure_ascii=False),
        )
    )
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
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
    span = []
    cursor = payload.start
    while cursor <= payload.end:
        span.append((user_id, cursor))
        cursor += timedelta(days=1)
    recalc = require_open(db, span, payload.confirm_closed)
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
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
    db.commit()
    return {"ok": True, "created": created}


@router.delete("/users/{user_id}/absences/{day}")
def delete_absence(
    user_id: int,
    day: date,
    request: Request,
    db: Session = Depends(get_db),
    confirm_closed: bool = Query(False),
):
    actor = _actor(request, db)
    row = db.scalar(select(Absence).where(Absence.user_id == user_id, Absence.day == day))
    if not row:
        raise HTTPException(404, "Keine Abwesenheit")
    recalc = require_open(db, [(user_id, day)], confirm_closed)
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
    db.flush()
    recalculate_pairs(db, recalc, actor.id)
    db.commit()
    return {"ok": True}


ISSUE_KEYS = ("missing_day", "checkout_missing", "break_short", "break_short_9h", "break_long", "over_10h")


@router.get("/closings")
def list_closings(request: Request, db: Session = Depends(get_db)):
    _actor_admin(request, db)
    rows = db.execute(
        select(
            MonthClosing.year,
            MonthClosing.month,
            func.count(MonthClosing.id),
            func.min(MonthClosing.closed_at),
            func.max(MonthClosing.closed_at),
        )
        .group_by(MonthClosing.year, MonthClosing.month)
        .order_by(MonthClosing.year.desc(), MonthClosing.month.desc())
    )
    return {
        "months": [
            {
                "year": year,
                "month": month,
                "people": people,
                "closed_at": (closed_max or closed_min).isoformat() if (closed_max or closed_min) else None,
            }
            for year, month, people, closed_min, closed_max in rows
        ]
    }


@router.get("/closings/job")
def closing_job(request: Request, db: Session = Depends(get_db)):
    _actor_admin(request, db)
    return job_status()


@router.get("/closings/{year}/{month}")
def closing_detail(year: int, month: int, request: Request, db: Session = Depends(get_db)):
    _actor_admin(request, db)
    if not 1 <= month <= 12:
        raise HTTPException(400, "Ungültiger Monat")
    rows = db.execute(
        select(MonthClosing, User)
        .join(User, User.id == MonthClosing.user_id)
        .where(MonthClosing.year == year, MonthClosing.month == month)
    )
    people = [
        {
            "user_id": user.id,
            "display_name": user.display_name,
            "flex_hours": row.flex_hours,
            "opening_balance_hours": user.opening_balance_hours,
            "opening_balance_on": user.opening_balance_on.isoformat() if user.opening_balance_on else None,
        }
        for row, user in rows
    ]
    people.sort(key=lambda item: name_sort_key(item["display_name"]))
    return {
        "year": year,
        "month": month,
        "people": people,
    }


@router.post("/closings")
def create_closing(payload: ClosingMonthIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor_admin(request, db)
    return start_close(payload.year, payload.month, actor.id)


@router.post("/closings/{year}/{month}/recalculate")
def recalculate_closing(year: int, month: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor_admin(request, db)
    return start_recalculate(year, month, actor.id)


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
    users = sorted(db.scalars(_user_with_rels()), key=_by_name)
    timelines = load_timelines(db, [u.id for u in users])
    frozen_map = load_frozen_map(db, [u.id for u in users])
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
        day_models = load_day_models(db, user.id, start, last)
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
                frozen=frozen_map.get((user.id, cur.year, cur.month)),
                model_override=day_models.get(cur),
            )
            if cur <= today:
                work += float(summary["work_hours"] or 0)
                soll += float(summary["soll_hours"] or 0)
                delta += float(summary["delta_hours"] or 0)
            cur += timedelta(days=1)
        total_flex = listed_total(db, user, today)
        people.append(
            {
                "user_id": user.id,
                "work_hours": work,
                "soll_hours": soll,
                "delta_hours": delta,
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
            _user_with_rels()
            .where(User.active.is_(True), User.role.in_(("employee", "supervisor")))
        )
    )
    users.sort(key=_by_name)
    timelines = load_timelines(db, [u.id for u in users])
    frozen_map = load_frozen_map(db, [u.id for u in users])
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
        day_models = load_day_models(db, user.id, start, last)
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
                frozen=frozen_map.get((user.id, cur.year, cur.month)),
                model_override=day_models.get(cur),
            )
            issues = [w for w in summary["warnings"] if w in counts or w.startswith("break_short:")]
            if issues:
                for w in issues:
                    counts[w] = counts.get(w, 0) + 1
                flagged.append({"date": summary["date"], "warnings": issues})
            cur += timedelta(days=1)
        total = sum(counts.values())
        if total == 0:
            continue
        rows.append(
            {
                "user": _user_out(user),
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
    _actor_full(request, db)
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
    _actor_full(request, db)
    q = _user_with_rels()
    if user_id:
        q = q.where(User.id == user_id)
    users = sorted(db.scalars(q), key=_by_name)
    timelines = load_timelines(db, [u.id for u in users])
    frozen_map = load_frozen_map(db, [u.id for u in users])
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
        day_models = load_day_models(db, user.id, start, last)
        cur = start
        while cur < end:
            day = summarize_user_day(
                user,
                punches,
                cur,
                timelines.get(user.id, []),
                absence=absences.get(cur),
                calendar=cal.get(cur),
                frozen=frozen_map.get((user.id, cur.year, cur.month)),
                model_override=day_models.get(cur),
            )
            if day["work_hours"] or day["first_in"] or day["warnings"] or day["absence"] or day.get("calendar"):
                day_cal = day.get("calendar") or {}
                writer.writerow(
                    [
                        safe_csv_cell(cell)
                        for cell in [
                            user.display_name,
                            day["date"],
                            day["first_in"] or "",
                            day["last_out"] or "",
                            format_hm(day["work_hours"]),
                            format_hm(day["break_hours"]),
                            format_hm(day["soll_hours"]),
                            format_hm(day["delta_hours"], signed=True),
                            (day["absence"] or {}).get("kind", "") if day["absence"] else day_cal.get("name", ""),
                            ",".join(_warn_de(w) for w in day["warnings"]),
                        ]
                    ]
                )
            cur += timedelta(days=1)
    payload = "\ufeff" + buf.getvalue()
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="zeiten-{month}.csv"'},
    )
