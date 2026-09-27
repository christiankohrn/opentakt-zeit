#!/usr/bin/env python3
"""Raise the nginx proxy timeout on an already installed site.

Certbot keeps its own server block. A template change alone does not reach it.
"""
from __future__ import annotations

import re
from pathlib import Path

SITE = Path("/etc/nginx/sites-available/zeiterfassung")
TIMEOUT = "300s"


def main() -> int:
    if not SITE.is_file():
        print("nginx-Site fehlt:", SITE)
        return 0
    text = SITE.read_text(encoding="utf-8")
    updated = re.sub(r"proxy_read_timeout\s+\d+s\s*;", f"proxy_read_timeout {TIMEOUT};", text)
    if "proxy_read_timeout" not in updated:
        updated = updated.replace(
            "proxy_pass http://127.0.0.1:8000;",
            f"proxy_pass http://127.0.0.1:8000;\n        proxy_read_timeout {TIMEOUT};",
        )
    if updated == text:
        print(f"proxy_read_timeout bereits {TIMEOUT}")
        return 0
    SITE.write_text(updated, encoding="utf-8")
    print(f"proxy_read_timeout {TIMEOUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
