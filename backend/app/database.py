from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_config


class Base(DeclarativeBase):
    pass


def _sqlite_url(path: str) -> str:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        p = Path(__file__).resolve().parents[2] / "data" / "app.db"
        p.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{p.as_posix()}"


def make_engine():
    cfg = get_config()
    engine = create_engine(
        _sqlite_url(cfg.database_path),
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _connection_record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def ensure_schema() -> None:
    from app.models import Base as ModelBase, User
    from app.workmodels import ensure_initial_assignment

    ModelBase.metadata.create_all(bind=engine)
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    alters: list[str] = []
    if "auto_break" not in cols:
        alters.append("ALTER TABLE users ADD COLUMN auto_break BOOLEAN NOT NULL DEFAULT 0")
    if "transponder_id" not in cols:
        alters.append("ALTER TABLE users ADD COLUMN transponder_id VARCHAR(80)")
    if "web_login" not in cols:
        alters.append("ALTER TABLE users ADD COLUMN web_login BOOLEAN NOT NULL DEFAULT 1")
    if "session_rev" not in cols:
        alters.append("ALTER TABLE users ADD COLUMN session_rev INTEGER NOT NULL DEFAULT 0")
    if "hired_on" not in cols:
        alters.append("ALTER TABLE users ADD COLUMN hired_on DATE")
    if "left_on" not in cols:
        alters.append("ALTER TABLE users ADD COLUMN left_on DATE")
    org_cols = {c["name"] for c in inspect(engine).get_columns("org_settings")} if inspect(engine).has_table("org_settings") else set()
    if "smtp_configured" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN smtp_configured BOOLEAN NOT NULL DEFAULT 0")
    if "smtp_enabled" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN smtp_enabled BOOLEAN NOT NULL DEFAULT 0")
    if "smtp_host" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN smtp_host VARCHAR(200) NOT NULL DEFAULT ''")
    if "smtp_port" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN smtp_port INTEGER NOT NULL DEFAULT 587")
    if "smtp_username" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN smtp_username VARCHAR(200) NOT NULL DEFAULT ''")
    if "smtp_password" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN smtp_password VARCHAR(400) NOT NULL DEFAULT ''")
    if "smtp_from" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN smtp_from VARCHAR(200) NOT NULL DEFAULT ''")
    if "smtp_use_tls" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN smtp_use_tls BOOLEAN NOT NULL DEFAULT 1")
    if "smtp_use_ssl" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN smtp_use_ssl BOOLEAN NOT NULL DEFAULT 0")
    if "dfcom_poll_enabled" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN dfcom_poll_enabled BOOLEAN NOT NULL DEFAULT 0")
    if "dfcom_poll_dry_run" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN dfcom_poll_dry_run BOOLEAN NOT NULL DEFAULT 1")
    if "dfcom_poll_interval_sec" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN dfcom_poll_interval_sec INTEGER NOT NULL DEFAULT 20")
    if "dfcom_sync_lists" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN dfcom_sync_lists BOOLEAN NOT NULL DEFAULT 1")
    if "dfcom_last_poll" not in org_cols:
        alters.append("ALTER TABLE org_settings ADD COLUMN dfcom_last_poll TEXT")
    term_cols = (
        {c["name"] for c in inspect(engine).get_columns("terminal_devices")}
        if inspect(engine).has_table("terminal_devices")
        else set()
    )
    if "last_list_hash" not in term_cols:
        alters.append("ALTER TABLE terminal_devices ADD COLUMN last_list_hash VARCHAR(64) NOT NULL DEFAULT ''")
    if alters:
        with engine.begin() as conn:
            for stmt in alters:
                conn.execute(text(stmt))
    with engine.begin() as conn:
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_transponder_id ON users (transponder_id)"))
        conn.execute(text("UPDATE users SET hired_on = date(created_at) WHERE hired_on IS NULL"))
    db = SessionLocal()
    try:
        for user in db.scalars(select(User)):
            ensure_initial_assignment(db, user)
        from app.models import OrgSettings
        from app.config import get_config

        if db.get(OrgSettings, 1) is None:
            db.add(OrgSettings(id=1, bundesland=(get_config().bundesland or "NW").upper()))
        db.commit()
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
