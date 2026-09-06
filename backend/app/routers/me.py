from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import as_local, bump_session_rev, current_user, local_day_bounds, now_utc, write_session
from app.balance import account_hours, days_in_range, month_days
from app.config import get_config
from app.database import get_db
from app.models import AuditEvent, Punch, User
from app.punches import record_punch
from app.schemas import PasswordChangeIn, PunchIn, PunchOut, StatusOut
from app.security import hash_password, verify_password
from app.timecalc import allowed_kinds, status_from_punches

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

