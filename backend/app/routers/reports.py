from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from app.auth import as_local, current_user, now_utc, require_hr
from app.config import get_config
from app.database import get_db
from app.models import User
from app.pdf import de_date, de_num, table_pdf
from app.reports import (
    VACATION_NOTE,
    format_de_date,
    format_month_label,
    journal_report,
    jubilees_report,
    month_balances_report,
    night_hours_report,
    sick_days_report,
    year_bounds,
)

router = APIRouter(prefix="/hr/reports", tags=["reports"])


def _actor(request: Request, db: Session) -> User:
    return require_hr(current_user(request, db))


def _org() -> str:
    return get_config().org_name


def _csv_response(filename: str, headers: list[str], rows: list[list[object]]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(headers)
    writer.writerows(rows)
    payload = "\ufeff" + buf.getvalue()
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _pdf_response(filename: str, payload: bytes) -> Response:
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _want_csv(request: Request, fmt: str | None) -> bool:
    return (fmt or "").lower() == "csv" or request.url.path.endswith(".csv")


def _want_pdf(request: Request, fmt: str | None) -> bool:
    return (fmt or "").lower() == "pdf" or request.url.path.endswith(".pdf")


def _parse_user_ids(raw: str | None) -> set[int] | None:
    if raw is None:
        return None
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        return set()
    try:
        return {int(part) for part in parts}
    except ValueError as exc:
        raise HTTPException(400, "user_ids ungültig") from exc


def _period(year: int | None, from_day: date | None, to_day: date | None) -> tuple[date, date]:
    if from_day is not None or to_day is not None:
        if from_day is None or to_day is None:
            raise HTTPException(400, "Zeitraum von und bis angeben")
        if from_day > to_day:
            raise HTTPException(400, "Zeitraum ungültig")
        return from_day, to_day
    if year is None:
        raise HTTPException(400, "Jahr oder Zeitraum angeben")
    return year_bounds(year)


@router.get("/sick-days")
@router.get("/sick-days.csv")
@router.get("/sick-days.pdf")
def sick_days(
    request: Request,
    db: Session = Depends(get_db),
    year: int | None = Query(None, ge=1990, le=2100),
    from_day: date | None = Query(None, alias="from"),
    to_day: date | None = Query(None, alias="to"),
    user_ids: str | None = Query(None),
    format: str | None = Query(None, alias="format"),
):
    _actor(request, db)
    start, end = _period(year, from_day, to_day)
    people = sick_days_report(db, start, end, _parse_user_ids(user_ids))
    subtitle = f"{format_de_date(start)} – {format_de_date(end)}"
    if _want_pdf(request, format):
        total = sum(row["sick_days"] for row in people)
        return _pdf_response(
            f"krankheitstage-{start.isoformat()}-{end.isoformat()}.pdf",
            table_pdf(
                title="Krankheitstage",
                subtitle=subtitle,
                org=_org(),
                columns=[("Name", 0.7, "L"), ("Krankheitstage", 0.3, "R")],
                rows=[[row["display_name"], str(row["sick_days"])] for row in people],
                totals=["Summe", str(total)] if people else None,
            ),
        )
    if _want_csv(request, format):
        return _csv_response(
            f"krankheitstage-{start.isoformat()}-{end.isoformat()}.csv",
            ["Name", "Krankheitstage"],
            [[row["display_name"], row["sick_days"]] for row in people],
        )
    return {"from": start.isoformat(), "to": end.isoformat(), "people": people}


@router.get("/month-balances")
@router.get("/month-balances.csv")
@router.get("/month-balances.pdf")
def month_balances(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    as_of: date | None = Query(None),
    format: str | None = Query(None, alias="format"),
):
    _actor(request, db)
    stichtag = as_of or as_local(now_utc()).date()
    people = month_balances_report(db, month, as_of=stichtag)
    subtitle = f"{format_month_label(month)}, Stichtag {format_de_date(stichtag)}"
    csv_headers = ["Name", "Ist", "Soll", "Diff", "Vortrag", "Gesamt", "Krank", "Urlaub", "Urlaub geplant"]
    csv_rows = [
        [
            row["display_name"],
            de_num(row["work_hours"], 2),
            de_num(row["soll_hours"], 2),
            de_num(row["delta_hours"], 1, signed=True),
            de_num(row["carry_hours"], 1, signed=True),
            de_num(row["total_hours"], 1, signed=True),
            row["sick_days"],
            row["vacation_days"],
            row["vacation_planned_days"],
        ]
        for row in people
    ]
    if _want_pdf(request, format):
        totals = None
        if people:
            totals = [
                "Summe",
                de_num(sum(row["work_hours"] for row in people), 2),
                de_num(sum(row["soll_hours"] for row in people), 2),
                de_num(sum(row["delta_hours"] for row in people), 1, signed=True),
                de_num(sum(row["carry_hours"] for row in people), 1, signed=True),
                de_num(sum(row["total_hours"] for row in people), 1, signed=True),
                str(sum(row["sick_days"] for row in people)),
                str(sum(row["vacation_days"] for row in people)),
                str(sum(row["vacation_planned_days"] for row in people)),
            ]
        return _pdf_response(
            f"salden-{month}-stichtag-{stichtag.isoformat()}.pdf",
            table_pdf(
                title="Monatssalden",
                subtitle=subtitle,
                org=_org(),
                landscape=True,
                note=VACATION_NOTE,
                columns=[
                    ("Name", 0.18, "L"),
                    ("Ist", 0.09, "R"),
                    ("Soll", 0.09, "R"),
                    ("Diff", 0.09, "R"),
                    ("Vortrag", 0.1, "R"),
                    ("Gesamt", 0.1, "R"),
                    ("Krank", 0.09, "R"),
                    ("Urlaub", 0.1, "R"),
                    ("Urlaub geplant", 0.16, "R"),
                ],
                rows=[
                    [
                        row["display_name"],
                        de_num(row["work_hours"], 2),
                        de_num(row["soll_hours"], 2),
                        de_num(row["delta_hours"], 1, signed=True),
                        de_num(row["carry_hours"], 1, signed=True),
                        de_num(row["total_hours"], 1, signed=True),
                        str(row["sick_days"]),
                        str(row["vacation_days"]),
                        str(row["vacation_planned_days"]),
                    ]
                    for row in people
                ],
                totals=totals,
            ),
        )
    if _want_csv(request, format):
        return _csv_response(f"salden-{month}-stichtag-{stichtag.isoformat()}.csv", csv_headers, csv_rows)
    return {
        "month": month,
        "as_of": stichtag.isoformat(),
        "note": VACATION_NOTE,
        "people": people,
    }


@router.get("/jubilees")
@router.get("/jubilees.csv")
@router.get("/jubilees.pdf")
def jubilees(
    request: Request,
    db: Session = Depends(get_db),
    year: int = Query(..., ge=1990, le=2100),
    half: int = Query(..., ge=1, le=2),
    format: str | None = Query(None, alias="format"),
):
    _actor(request, db)
    events = jubilees_report(db, year, half)
    half_label = "1. Halbjahr" if half == 1 else "2. Halbjahr"
    subtitle = f"{half_label} {year}"
    if _want_pdf(request, format):
        return _pdf_response(
            f"jubilaeen-{year}-hj{half}.pdf",
            table_pdf(
                title="Jubiläen",
                subtitle=subtitle,
                org=_org(),
                columns=[
                    ("Datum", 0.18, "L"),
                    ("Name", 0.42, "L"),
                    ("Art", 0.28, "L"),
                    ("Jahre", 0.12, "R"),
                ],
                rows=[[de_date(row["date"]), row["display_name"], row["label"], str(row["years"])] for row in events],
            ),
        )
    if _want_csv(request, format):
        return _csv_response(
            f"jubilaeen-{year}-hj{half}.csv",
            ["Name", "Datum", "Art", "Jahre"],
            [[row["display_name"], row["date"], row["label"], row["years"]] for row in events],
        )
    return {"year": year, "half": half, "events": events}


@router.get("/night-hours")
@router.get("/night-hours.csv")
@router.get("/night-hours.pdf")
def night_hours(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    format: str | None = Query(None, alias="format"),
):
    _actor(request, db)
    people = night_hours_report(db, month)
    subtitle = format_month_label(month)
    if _want_pdf(request, format):
        totals = None
        if people:
            totals = [
                "Summe",
                de_num(sum(row["hours_20_24"] for row in people), 2),
                de_num(sum(row["hours_0_4"] for row in people), 2),
                de_num(sum(row["hours_4_6"] for row in people), 2),
                de_num(sum(row["hours_1_plus_3"] for row in people), 2),
            ]
        return _pdf_response(
            f"nachtstunden-{month}.pdf",
            table_pdf(
                title="Nachtstunden",
                subtitle=subtitle,
                org=_org(),
                columns=[
                    ("Name", 0.36, "L"),
                    ("20–24", 0.16, "R"),
                    ("0–4", 0.16, "R"),
                    ("4–6", 0.16, "R"),
                    ("1+3", 0.16, "R"),
                ],
                rows=[
                    [
                        row["display_name"],
                        de_num(row["hours_20_24"], 2),
                        de_num(row["hours_0_4"], 2),
                        de_num(row["hours_4_6"], 2),
                        de_num(row["hours_1_plus_3"], 2),
                    ]
                    for row in people
                ],
                totals=totals,
                note="Arbeitsintervalle aus Stempeln. Auto-Pause wird nicht abgezogen. 1+3 = 20–24 plus 4–6.",
            ),
        )
    if _want_csv(request, format):
        return _csv_response(
            f"nachtstunden-{month}.csv",
            ["Name", "20-24", "0-4", "4-6", "1+3"],
            [
                [
                    row["display_name"],
                    de_num(row["hours_20_24"], 2),
                    de_num(row["hours_0_4"], 2),
                    de_num(row["hours_4_6"], 2),
                    de_num(row["hours_1_plus_3"], 2),
                ]
                for row in people
            ],
        )
    return {"month": month, "people": people}


@router.get("/journal.pdf")
def journal(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Query(...),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    _actor(request, db)
    user = db.scalar(select(User).options(selectinload(User.work_model)).where(User.id == user_id))
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    report = journal_report(db, user, month)
    rows: list[list[str]] = []
    for row in report["rows"]:
        if row["type"] == "day":
                work = de_num(row["work_hours"], 2) if row["work_hours"] else "-"
        else:
            work = de_num(row["work_hours"], 2)
        rows.append(
            [
                row["label"],
                row["booking"],
                work,
                de_num(row["soll_hours"], 2),
                de_num(row["delta_hours"], 2, signed=True),
            ]
        )
    safe_name = "".join(ch if ch.isalnum() else "-" for ch in report["display_name"]).strip("-")
    return _pdf_response(
        f"journal-{safe_name}-{month}.pdf",
        table_pdf(
            title=f"Journal {report['display_name']}",
            subtitle=report["month_label"],
            org=_org(),
            columns=[
                ("Tag", 0.16, "L"),
                ("Buchung", 0.48, "L"),
                ("Ist", 0.12, "R"),
                ("Soll", 0.12, "R"),
                ("Konto", 0.12, "R"),
            ],
            rows=rows,
        ),
    )
