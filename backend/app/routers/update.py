from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import update_service
from app.auth import current_user, require_admin
from app.config import get_config
from app.database import get_db
from app.models import AuditEvent, User

router = APIRouter(prefix="/hr/update", tags=["update"])


def _actor_admin(request: Request, db: Session) -> User:
    return require_admin(current_user(request, db))


@router.get("/status")
def get_status(request: Request, db: Session = Depends(get_db)):
    _actor_admin(request, db)
    return update_service.status_payload()


@router.post("/check")
def check(request: Request, db: Session = Depends(get_db)):
    _actor_admin(request, db)
    cfg = get_config()
    installed = update_service.local_install_info()
    try:
        result = update_service.check_remote(cfg, installed.get("commit"))
    except update_service.UpdateCheckError as exc:
        raise HTTPException(502, str(exc)) from exc
    update_service.write_status_file({**result, "last_check": update_service.now_iso()})
    return update_service.status_payload(cfg)


@router.post("/apply", status_code=202)
def apply(request: Request, db: Session = Depends(get_db)):
    actor = _actor_admin(request, db)
    payload = update_service.request_update(actor.username, actor.id)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="update.apply",
            entity_type="system",
            entity_id="update",
            payload=json.dumps({"by": actor.username}),
        )
    )
    db.commit()
    return payload
