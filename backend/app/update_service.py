from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

from app.branding import REPO_URL, UPDATE_BRANCH
from app.config import AppConfig, get_config
from app.routers.health import APP_VERSION

REQUEST_FILE = "update.request"
STATUS_FILE = "update-status.json"
VERSION_FILE = "version.json"
LOG_FILE = "update.log"
LOG_TAIL_LINES = 30
GITHUB_TIMEOUT = 10.0


class UpdateCheckError(Exception):
    """Der Stand auf GitHub ließ sich nicht ermitteln (Text ist UI-tauglich)."""


def app_root() -> Path:
    # backend/app/update_service.py -> backend/.. = Repo-Root bzw. /opt/zeiterfassung
    return Path(__file__).resolve().parents[2]


def data_dir(cfg: AppConfig | None = None) -> Path:
    cfg = cfg or get_config()
    path = Path(cfg.database_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.parent


def _api_repo() -> str:
    # https://github.com/christiankohrn/opentakt-zeit -> christiankohrn/opentakt-zeit
    return urlparse(REPO_URL).path.strip("/")


def update_supported(cfg: AppConfig | None = None) -> tuple[bool, str | None]:
    """One-Button-Update gibt es nur auf dem Server (systemd-Layout + Produktion)."""
    cfg = cfg or get_config()
    script = app_root() / "deploy" / "update.sh"
    if cfg.environment != "production" or not script.is_file():
        return False, "Das One-Button-Update gibt es nur auf dem Server."
    return True, None


def _read_version_file() -> dict:
    path = data_dir() / VERSION_FILE
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, ValueError):
        pass
    return {}


def _git_head(root: Path) -> dict:
    try:
        sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        info = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%cI%n%s"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return {}
    if not sha:
        return {}
    return {
        "commit": sha,
        "commit_date": info[0].strip() if info else None,
        "message": info[1].strip() if len(info) > 1 else "",
    }


def local_install_info() -> dict:
    info: dict = {"version": APP_VERSION, "commit": None, "commit_date": None, "message": ""}
    stored = _read_version_file()
    if stored.get("commit"):
        info.update({k: stored.get(k) for k in ("commit", "commit_date", "message")})
        return info
    info.update(_git_head(app_root()))
    return info


def fetch_json(url: str, cfg: AppConfig) -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Opentakt-Zeit/update-check"}
    token = (cfg.github_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        res = httpx.get(url, headers=headers, timeout=GITHUB_TIMEOUT)
    except httpx.TimeoutException:
        raise UpdateCheckError("GitHub antwortet nicht (Zeitüberschreitung). Später erneut versuchen.")
    except httpx.HTTPError:
        raise UpdateCheckError("GitHub ist nicht erreichbar. Netzwerk des Servers prüfen.")
    if res.status_code == 403 and "rate limit" in res.text.lower():
        raise UpdateCheckError("GitHub-Limit erreicht (zu viele Abfragen). Später erneut versuchen.")
    if res.status_code == 404:
        raise UpdateCheckError(f"Branch {UPDATE_BRANCH!r} auf GitHub nicht gefunden.")
    if res.status_code >= 400:
        raise UpdateCheckError(f"GitHub meldet Fehler {res.status_code}. Später erneut versuchen.")
    try:
        data = res.json()
    except ValueError:
        raise UpdateCheckError("GitHub hat unverständlich geantwortet. Später erneut versuchen.")
    return data if isinstance(data, dict) else {}


def check_remote(cfg: AppConfig, local_commit: str | None) -> dict:
    """Fragt den GitHub-Stand ab und vergleicht mit dem installierten Commit."""
    api = f"https://api.github.com/repos/{_api_repo()}"
    head = fetch_json(f"{api}/commits/{UPDATE_BRANCH}", cfg)
    sha = (head.get("sha") or "").strip()
    if not sha:
        raise UpdateCheckError("GitHub hat keinen Commit geliefert. Später erneut versuchen.")
    inner = head.get("commit") or {}
    committer = inner.get("committer") or {}
    remote = {
        "commit": sha,
        "commit_short": sha[:7],
        "date": committer.get("date"),
        "message": str(inner.get("message") or "").splitlines()[0][:160] if inner.get("message") else "",
        "url": head.get("html_url") or f"{REPO_URL}/commit/{sha}",
    }
    comparison = "unknown"
    behind_by: int | None = None
    if local_commit:
        cmp = fetch_json(f"{api}/compare/{local_commit}...{sha}", cfg)
        status = (cmp.get("status") or "").strip()
        if status == "identical":
            comparison = "current"
            behind_by = 0
        elif status == "behind":
            comparison = "behind"
            behind_by = int(cmp.get("behind_by") or 0)
        elif status == "ahead":
            comparison = "ahead"
            behind_by = 0
        elif status == "diverged":
            comparison = "diverged"
            behind_by = int(cmp.get("behind_by") or 0)
    return {"remote": remote, "comparison": comparison, "behind_by": behind_by}


def _default_status() -> dict:
    return {
        "remote": None,
        "comparison": "unknown",
        "behind_by": None,
        "last_check": None,
        "update": {"state": "idle"},
    }


def read_status_file() -> dict:
    merged = _default_status()
    try:
        path = data_dir() / STATUS_FILE
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged.update(data)
    except (OSError, ValueError):
        pass
    if not isinstance(merged.get("update"), dict):
        merged["update"] = {"state": "idle"}
    return merged


def write_status_file(patch: dict) -> dict:
    current = read_status_file()
    current.update(patch)
    path = data_dir() / STATUS_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return current


def _log_tail() -> list[str]:
    try:
        path = data_dir() / LOG_FILE
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-LOG_TAIL_LINES:]
    except OSError:
        return []


def status_payload(cfg: AppConfig | None = None) -> dict:
    cfg = cfg or get_config()
    supported, reason = update_supported(cfg)
    installed = local_install_info()
    sha = installed.get("commit") or ""
    cached = read_status_file()
    update = dict(cached.get("update") or {"state": "idle"})
    update["log_tail"] = _log_tail()
    return {
        "supported": supported,
        "unsupported_reason": reason,
        "installed": {
            "version": installed.get("version"),
            "commit": sha or None,
            "commit_short": sha[:7] if sha else None,
            "commit_date": installed.get("commit_date"),
            "message": installed.get("message") or "",
        },
        "source": {"repo": _api_repo(), "branch": UPDATE_BRANCH, "url": REPO_URL},
        "remote": cached.get("remote"),
        "comparison": cached.get("comparison", "unknown"),
        "behind_by": cached.get("behind_by"),
        "last_check": cached.get("last_check"),
        "update": update,
    }


def now_iso() -> str:
    return datetime.now(tz=ZoneInfo("UTC")).isoformat()


def request_update(actor_name: str, actor_id: int) -> dict:
    cfg = get_config()
    supported, reason = update_supported(cfg)
    if not supported:
        raise HTTPException(409, reason or "Update auf diesem System nicht möglich.")
    state = (read_status_file().get("update") or {}).get("state")
    if state == "running":
        raise HTTPException(409, "Ein Update läuft bereits.")
    installed = local_install_info()
    directory = data_dir(cfg)
    directory.mkdir(parents=True, exist_ok=True)
    # Direkt schreiben (kein Rename): Die systemd-Path-Unit reagiert auf die Änderung.
    (directory / REQUEST_FILE).write_text(
        json.dumps(
            {"requested_by": actor_name, "requested_by_id": actor_id, "requested_at": now_iso()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    write_status_file(
        {
            "update": {
                "state": "running",
                "requested_by": actor_name,
                "started_at": now_iso(),
                "from_commit": (installed.get("commit") or "")[:7] or None,
                "to_commit": None,
                "finished_at": None,
                "error": None,
            }
        }
    )
    return status_payload(cfg)
