from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.branding import PRODUCT_NAME
from app.config import get_config
from app.database import SessionLocal, ensure_schema
from app.routers import auth, health, hr, me, terminals
from app.routers.health import APP_VERSION
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    cfg = get_config()
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
    app.include_router(terminals.router, prefix="/api")

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
