from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.auth import local_tz
from app.config import get_config


def _backup_root() -> Path:
    cfg = get_config()
    if cfg.backup_dir:
        root = Path(cfg.backup_dir)
    else:
        root = Path(cfg.database_path).resolve().parent / "backups"
    (root / "daily").mkdir(parents=True, exist_ok=True)
    (root / "monthly").mkdir(parents=True, exist_ok=True)
    (root / "yearly").mkdir(parents=True, exist_ok=True)
    return root


def _copy_sqlite(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dest.as_posix())
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _prune(folder: Path, keep: int) -> None:
    files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix == ".db"), reverse=True)
    for stale in files[keep:]:
        stale.unlink()


def run() -> None:
    cfg = get_config()
    src = Path(cfg.database_path)
    if not src.is_file():
        raise SystemExit(f"Datenbank fehlt: {src}")
    now = datetime.now(tz=local_tz())
    root = _backup_root()
    daily = root / "daily" / f"{now:%Y-%m-%d}.db"
    monthly = root / "monthly" / f"{now:%Y-%m}.db"
    yearly = root / "yearly" / f"{now:%Y}.db"
    _copy_sqlite(src, daily)
    _copy_sqlite(src, monthly)
    _copy_sqlite(src, yearly)
    _prune(root / "daily", 30)
    _prune(root / "monthly", 12)
    _prune(root / "yearly", 2)
    print(f"Backup {daily} (Monat {monthly.name}, Jahr {yearly.name})")


if __name__ == "__main__":
    run()
