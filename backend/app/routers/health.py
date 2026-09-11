from fastapi import APIRouter

from app.config import get_config

router = APIRouter()

APP_VERSION = "0.1.0"


@router.get("/meta")
def meta():
    cfg = get_config()
    return {"org_name": cfg.org_name, "version": APP_VERSION}


@router.get("/health")
def health():
    cfg = get_config()
    from pathlib import Path
    from sqlalchemy import text
    from app.database import engine
    from app.dfcom import library_available

    db_ok = False
    esp_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("PRAGMA integrity_check"))
        db_ok = True
    except Exception:
        db_ok = False
    try:
        from app.database import SessionLocal
        from app.esp_service import effective_secret

        session = SessionLocal()
        try:
            esp_ok = bool(effective_secret(session))
        finally:
            session.close()
    except Exception:
        esp_ok = bool((cfg.esp_terminal_secret or "").strip())
    db_path = Path(cfg.database_path)
    disk_free = None
    try:
        import shutil

        disk_free = shutil.disk_usage(db_path.parent if db_path.parent.exists() else "/").free
    except Exception:
        pass
    return {
        "ok": db_ok,
        "environment": cfg.environment,
        "org": cfg.org_name,
        "db": db_ok,
        "disk_free_bytes": disk_free,
        "dfcom_library": library_available(),
        "esp_terminal": esp_ok,
    }
