from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_config
from app.models import User
from app.security import verify_password

HR_ROLES = {"hr", "admin", "supervisor"}


def normalize_username(value: str) -> str:
    return value.strip().casefold()


def now_utc() -> datetime:
    return datetime.now(tz=ZoneInfo("UTC"))


def local_tz():
    return ZoneInfo(get_config().timezone)


def as_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(local_tz())


def local_day_bounds(day) -> tuple[datetime, datetime]:
    tz = local_tz()
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    end = start + timedelta(days=1)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def current_user(request: Request, db: Session) -> User:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet")
    user = db.get(User, uid)
    if not user or not user.active:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet")
    if int(request.session.get("rev") or 0) != int(user.session_rev or 0):
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet")
    return user


def write_session(request: Request, user: User) -> None:
    request.session.clear()
    request.session["uid"] = user.id
    request.session["rev"] = int(user.session_rev or 0)


def bump_session_rev(user: User) -> None:
    user.session_rev = int(user.session_rev or 0) + 1


def require_hr(user: User) -> User:
    if user.role not in HR_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung")
    return user


def require_admin(user: User) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur Administrator")
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    key = normalize_username(username)
    if not key:
        return None
    user = db.scalar(select(User).where(func.lower(User.username) == key))
    cfg = get_config()
    if user and user.auth_source == "local" and verify_password(password, user.password_hash):
        return user if user.active else None
    if cfg.ldap.enabled:
        from app.ldap_auth import try_ldap_login

        ldap_user = try_ldap_login(db, key, password, existing=user)
        if ldap_user:
            return ldap_user
    return None
