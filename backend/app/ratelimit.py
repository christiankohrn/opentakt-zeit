from __future__ import annotations

"""Brute-Force-Schutz für anonyme Auth-Endpunkte.

Zählt Fehlversuche je Client-IP in einem Sliding-Window und antwortet mit
429 + Retry-After, sobald das Budget aufgebraucht ist. Erfolgreiche
Anmeldungen löschen das Budget, damit legitime Nutzer hinter geteilten IPs
nicht ausgesperrt werden.

Der Speicher lebt im Prozess. Das passt zum Betrieb mit genau einem
Uvicorn-Worker; bei mehreren Prozessen gilt das Limit pro Prozess.
"""

from collections import deque
from time import monotonic

from fastapi import HTTPException, Request

LOGIN_MAX = 10
LOGIN_WINDOW = 600
MFA_MAX = 20
MFA_WINDOW = 600
PASSKEY_OPTIONS_MAX = 30
PASSKEY_OPTIONS_WINDOW = 600
PASSKEY_MAX = 10
PASSKEY_WINDOW = 600
FORGOT_MAX = 10
FORGOT_WINDOW = 3600
TOKEN_MAX = 30
TOKEN_WINDOW = 3600
ESP_MAX = 60
ESP_WINDOW = 3600
IMPORT_MAX = 30
IMPORT_WINDOW = 3600

MAX_KEYS = 10000

_hits: dict[str, deque[float]] = {}


def client_key(request: Request, scope: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{scope}:{host}"


def _prune(key: str, now: float, window: int) -> deque[float]:
    hits = _hits.get(key)
    if hits is None:
        hits = deque()
        _hits[key] = hits
    while hits and hits[0] <= now - window:
        hits.popleft()
    if len(_hits) > MAX_KEYS:
        for stale in [k for k, v in _hits.items() if not v]:
            del _hits[stale]
            if len(_hits) <= MAX_KEYS:
                break
    return hits


def check(key: str, limit: int, window: int) -> None:
    """429 auslösen, wenn das Budget für key aufgebraucht ist."""
    hits = _prune(key, monotonic(), window)
    if len(hits) >= limit:
        retry_after = max(1, int(hits[0] + window - monotonic()))
        raise HTTPException(
            status_code=429,
            detail="Zu viele Versuche. Bitte später erneut versuchen.",
            headers={"Retry-After": str(retry_after)},
        )


def record(key: str, window: int) -> None:
    """Einen Versuch für key zählen."""
    _prune(key, monotonic(), window).append(monotonic())


def attempt(key: str, limit: int, window: int) -> None:
    """Prüfen und zählen in einem Schritt (für Endpunkte ohne Erfolg/Misserfolg)."""
    check(key, limit, window)
    record(key, window)


def clear(key: str) -> None:
    """Budget für key zurücksetzen (nach erfolgreicher Anmeldung)."""
    _hits.pop(key, None)


def reset() -> None:
    """Alle Zähler löschen. Nur für Tests."""
    _hits.clear()
