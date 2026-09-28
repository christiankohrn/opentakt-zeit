from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from app.branding import PRODUCT_NAME
from app.config import get_config
from app.database import SessionLocal, ensure_schema
from app.dfcom_poll import start_background, stop_background
from app.models import User
from app.names import compose_display_name, split_person_name
from app.routers import auth, booking_import, dfcom_api, esp_terminal, health, hr, me, reports, terminals
from app.routers.health import APP_VERSION
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        changed = False
        for user in db.scalars(select(User)):
            if (user.first_name or "").strip() or (user.last_name or "").strip():
                display = compose_display_name(user.first_name, user.last_name)
            else:
                first, last = split_person_name(user.display_name)
                display = compose_display_name(first, last)
                if user.first_name != first or user.last_name != last:
                    user.first_name = first
                    user.last_name = last
                    changed = True
            if user.display_name != display:
                user.display_name = display
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()
    start_background()
    yield
    stop_background()


def create_app() -> FastAPI:
    cfg = get_config()
    if not cfg.is_dev and (cfg.secret_key or "").strip() in {"", "dev-only-change-me", "change-me"}:
        raise RuntimeError("secret_key steht noch auf dem Standardwert. Bitte in config.toml ändern.")
    app = FastAPI(title=PRODUCT_NAME, version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=cfg.secret_key,
        session_cookie="ze_session",
        https_only=cfg.public_url.startswith("https://"),
        same_site="lax",
        max_age=60 * 60 * 24 * 14,
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(me.router, prefix="/api")
    app.include_router(hr.router, prefix="/api")
    app.include_router(reports.router, prefix="/api")
    app.include_router(dfcom_api.router, prefix="/api")
    app.include_router(esp_terminal.router, prefix="/api")
    app.include_router(esp_terminal.hr_router, prefix="/api")
    app.include_router(terminals.router, prefix="/api")
    app.include_router(booking_import.router, prefix="/api")
    app.include_router(booking_import.hr_router, prefix="/api")

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404)
            candidate = dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
