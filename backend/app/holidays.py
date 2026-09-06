from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_config

STATES: dict[str, str] = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}

# State codes that observe the regional holiday.
_EPIPHANY = {"BW", "BY", "ST"}
_WOMENS_DAY = {"BE", "MV"}
_CORPUS_CHRISTI = {"BW", "BY", "HE", "NW", "RP", "SL"}
_ASSUMPTION = {"BY", "SL"}
_CHILDRENS_DAY = {"TH"}
_REFORMATION = {"BB", "HB", "HH", "MV", "NI", "SN", "ST", "SH", "TH"}
_ALL_SAINTS = {"BW", "BY", "NW", "RP", "SL"}


@dataclass(frozen=True)
class CalendarInfo:
    day: date
    kind: str  # holiday | company_off
    name: str
    source: str  # law | custom
    id: int | None = None


def easter(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month, day = divmod(h + ll - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _buss_und_bettag(year: int) -> date:
    # Wednesday before 23 November.
    d = date(year, 11, 23)
    while d.weekday() != 2:
        d -= timedelta(days=1)
    return d


def public_holidays(year: int, bundesland: str) -> dict[date, str]:
    land = (bundesland or "NW").upper()
    east = easter(year)
    days: dict[date, str] = {
        date(year, 1, 1): "Neujahr",
        east - timedelta(days=2): "Karfreitag",
        east + timedelta(days=1): "Ostermontag",
        date(year, 5, 1): "Tag der Arbeit",
        east + timedelta(days=39): "Christi Himmelfahrt",
        east + timedelta(days=50): "Pfingstmontag",
        date(year, 10, 3): "Tag der Deutschen Einheit",
        date(year, 12, 25): "1. Weihnachtstag",
        date(year, 12, 26): "2. Weihnachtstag",
    }
    if land in _EPIPHANY:
        days[date(year, 1, 6)] = "Heilige Drei Könige"
    if land in _WOMENS_DAY:
        days[date(year, 3, 8)] = "Internationaler Frauentag"
    if land in _CORPUS_CHRISTI:
        days[east + timedelta(days=60)] = "Fronleichnam"
    if land in _ASSUMPTION:
        days[date(year, 8, 15)] = "Mariä Himmelfahrt"
    if land in _CHILDRENS_DAY:
        days[date(year, 9, 20)] = "Weltkindertag"
    if land in _REFORMATION:
        days[date(year, 10, 31)] = "Reformationstag"
    if land in _ALL_SAINTS:
        days[date(year, 11, 1)] = "Allerheiligen"
    if land == "SN":
        days[_buss_und_bettag(year)] = "Buß- und Bettag"
    return days


def bundesland_of(db: Session) -> str:
    from app.models import OrgSettings

    row = db.get(OrgSettings, 1)
    if row and row.bundesland:
        return row.bundesland.upper()
    return (get_config().bundesland or "NW").upper()


def calendar_map(db: Session, start: date, last: date) -> dict[date, CalendarInfo]:
    from app.models import CalendarEntry

    land = bundesland_of(db)
    out: dict[date, CalendarInfo] = {}
    for year in range(start.year, last.year + 1):
        for day, name in public_holidays(year, land).items():
            if start <= day <= last:
                out[day] = CalendarInfo(day=day, kind="holiday", name=name, source="law")
    rows = db.scalars(select(CalendarEntry).where(CalendarEntry.day >= start, CalendarEntry.day <= last))
    for row in rows:
        out[row.day] = CalendarInfo(day=row.day, kind=row.kind, name=row.name, source="custom", id=row.id)
    return out


def year_calendar(db: Session, year: int) -> list[CalendarInfo]:
    start = date(year, 1, 1)
    last = date(year, 12, 31)
    mapping = calendar_map(db, start, last)
    return [mapping[d] for d in sorted(mapping)]
