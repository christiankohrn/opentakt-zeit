#!/usr/bin/env python3
"""Keep /api/terminals/datafox reachable over HTTP after Certbot's HTTPS redirect.

Datafox MasterIV firmware before 04.03.11 cannot speak TLS. Certbot's
`if ($host) { return 301 }` runs in the rewrite phase and would otherwise
redirect every booking request.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SITE = Path("/etc/nginx/sites-available/zeiterfassung")
MARKER = "location /api/terminals/datafox"

LOCATION = """
    location /api/terminals/datafox {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
"""


def _server_blocks(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"\bserver\s*\{", text):
        start = match.start()
        i = match.end() - 1
        depth = 0
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    spans.append((start, i + 1))
                    break
            i += 1
    return spans


def _listen_80(block: str) -> bool:
    return bool(re.search(r"listen\s+(?:\[::\]:)?80\b", block))


def _rewrite_http_block(block: str) -> str:
    block = re.sub(
        r"\n\s*if\s*\(\$host\s*=\s*[^)]+\)\s*\{\s*return\s+301\s+https://\$host\$request_uri;\s*\}",
        "\n",
        block,
        flags=re.S,
    )
    block = re.sub(r"\n\s*return\s+404;\s*# managed by Certbot", "\n", block)
    if MARKER not in block:
        brace = block.find("{")
        block = block[: brace + 1] + LOCATION + block[brace + 1 :]
    if not re.search(r"location\s+/[\s{]", block):
        block = block.rstrip()
        if block.endswith("}"):
            block = block[:-1] + "\n    location / {\n        return 301 https://$host$request_uri;\n    }\n}\n"
    return block


def main() -> int:
    if not SITE.is_file():
        print("nginx-Site fehlt:", SITE, file=sys.stderr)
        return 1
    text = SITE.read_text(encoding="utf-8")
    blocks = _server_blocks(text)
    http_spans = [span for span in blocks if _listen_80(text[span[0] : span[1]])]
    if not http_spans:
        print("Kein HTTP-Serverblock gefunden", file=sys.stderr)
        return 1
    changed = False
    # Rewrite from the end so earlier offsets stay valid.
    for start, end in reversed(http_spans):
        original = text[start:end]
        updated = _rewrite_http_block(original)
        if updated != original:
            text = text[:start] + updated + text[end:]
            changed = True
    if not changed and MARKER in text:
        print("HTTP-Pfad für Terminals bereits vorhanden")
        return 0
    if not changed:
        print("HTTP-Serverblock unverändert, prüfe manuell", file=sys.stderr)
        return 1
    SITE.write_text(text, encoding="utf-8")
    print("HTTP-Pfad für Terminals eingetragen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
