from __future__ import annotations

from datetime import date
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import as_local, now_utc
from app.balance import format_flex, month_flex_hours
from app.dfcom import RecordSchema, list_row_size, pack_list_rows
from app.models import Absence, User

PERSONAL_LIST_NAME = "personal"


def find_personal_list_id(schemas: dict[int, RecordSchema]) -> int | None:
    for list_id, schema in schemas.items():
        if schema.name.strip().lower() == PERSONAL_LIST_NAME:
            return list_id
    schema0 = schemas.get(0)
    if schema0 is not None and schema0.name.strip().lower() in {"", PERSONAL_LIST_NAME}:
        return 0
    return None


def vacation_taken_label(db: Session, user_id: int, year: int) -> str:
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    n = int(
        db.scalar(
            select(func.count())
            .select_from(Absence)
            .where(Absence.user_id == user_id, Absence.kind == "vacation", Absence.day >= start, Absence.day <= end)
        )
        or 0
    )
    if n <= 0:
        return ""
    return f"{n} T"


def personal_rows(db: Session) -> list[dict[str, str]]:
    today = as_local(now_utc()).date()
    users = list(
        db.scalars(select(User).where(User.active.is_(True), User.transponder_id.is_not(None)).order_by(User.id))
    )
    rows: list[dict[str, str]] = []
    for user in users:
        badge = (user.transponder_id or "").strip()
        if not badge:
            continue
        if user.left_on is not None and user.left_on < today:
            continue
        rows.append(
            {
                "KARTE": badge,
                "UKO": vacation_taken_label(db, user.id, today.year),
                "ZKO": format_flex(month_flex_hours(db, user)),
                "NAME": user.display_name or "",
                "KENNZEICHEN": "",
                "KARTE2": "",
            }
        )
    return rows


def packed_personal(schema: RecordSchema, rows: list[dict[str, str]]) -> tuple[bytes, int, int, str]:
    blob = pack_list_rows(schema, rows)
    row_size = list_row_size(schema)
    digest = sha256(blob).hexdigest()
    return blob, len(rows), row_size, digest
