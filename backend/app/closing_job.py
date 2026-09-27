"""Monatsabschluss außerhalb der HTTP-Anfrage, damit nginx nicht nach 60 Sekunden abbricht."""

from __future__ import annotations

import json
import logging
import threading

from sqlalchemy import and_, or_, select

from app.closings import assert_past_month, close_through, recalculate_pairs
from app.database import SessionLocal
from app.models import AuditEvent, MonthClosing

log = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "running": False,
    "kind": "",
    "year": 0,
    "month": 0,
    "done": 0,
    "total": 0,
    "rows": 0,
    "error": None,
}


def job_status() -> dict:
    with _lock:
        return dict(_state)


def _update(**fields) -> None:
    with _lock:
        _state.update(fields)


def _start(kind: str, year: int, month: int, target) -> dict:
    with _lock:
        if _state["running"]:
            return dict(_state)
        _state.update(
            {
                "running": True,
                "kind": kind,
                "year": year,
                "month": month,
                "done": 0,
                "total": 0,
                "rows": 0,
                "error": None,
            }
        )
        snapshot = dict(_state)
    threading.Thread(target=target, name=f"closing-{kind}", daemon=True).start()
    return snapshot


def start_close(year: int, month: int, actor_id: int) -> dict:
    assert_past_month(year, month)
    return _start("close", year, month, lambda: _run_close(year, month, actor_id))


def start_recalculate(year: int, month: int, actor_id: int) -> dict:
    assert_past_month(year, month)
    return _start("recalculate", year, month, lambda: _run_recalculate(year, month, actor_id))


def _run_close(year: int, month: int, actor_id: int) -> None:
    db = SessionLocal()
    try:
        def on_user(done: int, total: int, rows: int) -> None:
            if done:
                db.commit()
            _update(done=done, total=total, rows=rows)

        written = close_through(db, year, month, actor_id, on_user=on_user)
        db.add(
            AuditEvent(
                actor_id=actor_id,
                action="month.close",
                entity_type="month_closing",
                entity_id=f"{year:04d}-{month:02d}",
                payload=json.dumps({"year": year, "month": month, "rows": written}),
            )
        )
        db.commit()
        _update(running=False, rows=written, error=None)
    except Exception:
        log.exception("Monatsabschluss")
        db.rollback()
        _update(running=False, error="Der Abschluss ist fehlgeschlagen. Bitte erneut starten.")
    finally:
        db.close()


def _run_recalculate(year: int, month: int, actor_id: int) -> None:
    db = SessionLocal()
    try:
        user_ids = db.scalars(
            select(MonthClosing.user_id)
            .where(
                or_(
                    MonthClosing.year > year,
                    and_(MonthClosing.year == year, MonthClosing.month >= month),
                )
            )
            .distinct()
        ).all()
        pairs = [(user_id, year, month) for user_id in user_ids]

        def on_user(done: int, total: int) -> None:
            if done:
                db.commit()
            _update(done=done, total=total, rows=done)

        recalculate_pairs(db, pairs, actor_id, on_user=on_user)
        db.add(
            AuditEvent(
                actor_id=actor_id,
                action="month.recalculate",
                entity_type="month_closing",
                entity_id=f"{year:04d}-{month:02d}",
                payload=json.dumps({"year": year, "month": month, "people": len(pairs)}),
            )
        )
        db.commit()
        _update(running=False, rows=len(pairs), error=None)
    except Exception:
        log.exception("Abschluss neu rechnen")
        db.rollback()
        _update(running=False, error="Die Neuberechnung ist fehlgeschlagen. Bitte erneut starten.")
    finally:
        db.close()
