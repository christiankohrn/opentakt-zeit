from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import normalize_username
from app.config import get_config
from app.models import AuditEvent, Department, User, WorkModel, WorkModelAssignment
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
    produktion = Department(name="Produktion")
    lager = Department(name="Lager")
    db.add_all([produktion, lager])
    db.flush()
    # Absichtlich nur ein Administrator. Weitere bekannte Konten mit
    # bekannten Passwörtern wären ein Einfallstor; Personal legt der Admin
    # in der UI an. Der Seed-Admin muss beim ersten Login ein eigenes
    # Passwort vergeben.
    users = [
        User(
            username=normalize_username(cfg.seed.admin_username),
            display_name="Administrator",
            email="admin@localhost",
            password_hash=hash_password(cfg.seed.admin_password),
            role="admin",
            work_model_id=model.id,
            must_change_password=True,
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
