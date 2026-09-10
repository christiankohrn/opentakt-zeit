from __future__ import annotations

import re

from app.punches import KIND_LABELS

LINE_MAX = 21
DEFAULT_OK_LINE1 = "{first_name}"
DEFAULT_OK_LINE2 = "{kind} {flex_month}"

_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def clip_line(text: str, size: int = LINE_MAX) -> str:
    return " ".join((text or "").replace("\n", " ").replace("\r", " ").split())[:size]


def render_line(template: str, values: dict[str, str], *, size: int = LINE_MAX) -> str:
    out = template or ""
    for key, value in values.items():
        out = out.replace("{" + key + "}", value or "")
    out = _PLACEHOLDER.sub("", out)
    return clip_line(out, size)


def punch_values(
    *,
    display_name: str | None,
    kind: str | None,
    flex_month: str = "",
    flex_total: str = "",
) -> dict[str, str]:
    name = (display_name or "").strip()
    first = name.split()[0] if name else ""
    label = KIND_LABELS.get(kind or "", kind or "")
    return {
        "display_name": name,
        "first_name": first or "OK",
        "kind": label,
        "flex_month": flex_month,
        "flex_total": flex_total,
    }
