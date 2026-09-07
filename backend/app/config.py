from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.branding import PRODUCT_NAME


class SeedConfig(BaseModel):
    admin_username: str = "admin"
    admin_password: str = "change-me"
    hr_username: str = "personal"
    hr_password: str = "change-me"
    employee_username: str = "mitarbeiter"
    employee_password: str = "change-me"
    shift_username: str = "erika"
    shift_password: str = "change-me"


class SmtpConfig(BaseModel):
    enabled: bool = False
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = ""
    use_tls: bool = True
    use_ssl: bool = False


class LdapConfig(BaseModel):
    enabled: bool = False
    url: str = ""
    bind_dn: str = ""
    bind_password: str = ""
    user_base: str = ""
    user_filter: str = "(sAMAccountName={username})"
    group_hr: str = ""
    group_admin: str = ""


class AppConfig(BaseModel):
    environment: str = "development"
    secret_key: str = "dev-only-change-me"
    timezone: str = "Europe/Berlin"
    org_name: str = PRODUCT_NAME
    public_url: str = "http://127.0.0.1:8000"
    bundesland: str = "NW"
    database_path: str = "data/app.db"
    listen_host: str = "127.0.0.1"
    listen_port: int = 8000
    backup_dir: str = ""
    seed: SeedConfig = Field(default_factory=SeedConfig)
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    ldap: LdapConfig = Field(default_factory=LdapConfig)
    dfcom_lib: str = ""
    datafox_secret: str = ""

    @property
    def is_dev(self) -> bool:
        return self.environment in {"development", "dev", "local"}


def _candidate_paths() -> list[Path]:
    env = os.environ.get("ZEITERFASSUNG_CONFIG")
    if env:
        return [Path(env)]
    here = Path(__file__).resolve()
    return [
        Path("/etc/zeiterfassung/config.toml"),
        here.parents[2] / "config.toml",
        Path.cwd() / "config.toml",
    ]


def load_raw() -> dict[str, Any]:
    for path in _candidate_paths():
            try:
                if path.is_file():
                    with path.open("rb") as fh:
                        data = tomllib.load(fh)
                    data["_config_path"] = str(path)
                    return data
            except PermissionError:
                continue
    return {}


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    raw = load_raw()
    raw.pop("_config_path", None)
    return AppConfig.model_validate(raw)
