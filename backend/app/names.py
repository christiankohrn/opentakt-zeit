"""Anzeigename als Nachname, Vorname.

Gespeicherte Namen der Form „Vorname PU Nachname“: das erste Wort ist der
Vorname, alles nach dem ersten Leerzeichen der Nachname. Ein Komma stammt aus
einem früheren Lauf, der das letzte Wort als Nachname genommen hat, und wird
zuerst zurückgesetzt.
"""

from __future__ import annotations

_SORT = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


def _tidy(value: str | None) -> str:
    return " ".join((value or "").split())


def source_name(value: str | None) -> str:
    """Form „Vorname … Nachname“, auch wenn schon ein Komma gesetzt wurde."""
    name = _tidy(value)
    if "," not in name:
        return name
    before, _, after = name.partition(",")
    before = _tidy(before)
    after = _tidy(after)
    if before and after:
        return f"{after} {before}"
    return before or after


def split_person_name(value: str | None) -> tuple[str, str]:
    source = source_name(value)
    if not source:
        return "", ""
    first, _, rest = source.partition(" ")
    if not rest:
        return "", first
    return first, rest


def compose_display_name(first: str | None, last: str | None) -> str:
    first_name = _tidy(first)
    last_name = _tidy(last)
    if last_name and first_name:
        return f"{last_name}, {first_name}"
    return last_name or first_name


def format_person_name(value: str | None) -> str:
    first, last = split_person_name(value)
    return compose_display_name(first, last)


def given_name(value: str | None) -> str:
    first, last = split_person_name(value)
    if first:
        return first.split(" ")[0]
    return last.split(" ")[0] if last else ""


def name_sort_key(value: str | None) -> str:
    first, last = split_person_name(value)
    return f"{last} {first}".casefold().translate(_SORT)


def person_sort_key(first: str | None, last: str | None, display: str | None = None) -> str:
    if _tidy(first) or _tidy(last):
        return f"{_tidy(last)} {_tidy(first)}".casefold().translate(_SORT)
    return name_sort_key(display)
