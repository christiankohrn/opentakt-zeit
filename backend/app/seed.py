from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import normalize_username
from app.config import get_config
from app.models import AuditEvent, User, WorkModel, WorkModelAssignment
from app.security import hash_password
from app.workmodels import BACKFILL_FROM, ensure_initial_assignment


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)):
        return
    cfg = get_config()
    model = WorkModel(
        name="Vollzeit 40h Gleitzeit",
        kind="flextime",
        hours_mon=8,
        hours_tue=8,
        hours_wed=8,
        hours_thu=8,
        hours_fri=8,
        hours_sat=0,
        hours_sun=0,
    )
    db.add(model)
    db.flush()
    shift = WorkModel(
        name="Wechselschicht 3×8",
        kind="shift",
        hours_mon=8,
        hours_tue=8,
        hours_wed=8,
        hours_thu=8,
        hours_fri=8,
        hours_sat=0,
        hours_sun=0,
    )
    db.add(shift)
    db.flush()
    users = [
        User(
            username=normalize_username(cfg.seed.admin_username),
            display_name="Administrator",
            email="admin@localhost",
            password_hash=hash_password(cfg.seed.admin_password),
            role="admin",
            work_model_id=model.id,
        ),
        User(
            username=normalize_username(cfg.seed.hr_username),
            display_name="Personal",
            email="personal@localhost",
            password_hash=hash_password(cfg.seed.hr_password),
            role="hr",
            work_model_id=model.id,
        ),
        User(
            username=normalize_username(cfg.seed.employee_username),
            display_name="Max Mustermann",
            email="mitarbeiter@localhost",
            password_hash=hash_password(cfg.seed.employee_password),
            role="employee",
            work_model_id=model.id,
        ),
        User(
            username=normalize_username(cfg.seed.shift_username),
            display_name="Erika Schicht",
            email="erika@localhost",
            password_hash=hash_password(cfg.seed.shift_password),
            role="employee",
            work_model_id=shift.id,
        ),
    ]
    db.add_all(users)
    db.flush()
    for user in users:
        ensure_initial_assignment(db, user, valid_from=BACKFILL_FROM)
    db.add(
        AuditEvent(
            actor_id=users[0].id,
            action="seed",
            entity_type="system",
            entity_id="0",
            payload=json.dumps({"users": [u.username for u in users]}),
        )
    )
    db.commit()
