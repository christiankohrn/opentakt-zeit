from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import as_local, current_user, now_utc, require_hr
from app.config import get_config
from app.database import get_db
from app.models import User
from app.pdf import ReportPDF, de_date, de_days, de_num, table_pdf
from app.reports import (
    JOURNAL_ACCOUNT_NOTE,
    VACATION_NOTE,
    format_de_date,
    format_month_label,
    journal_people,
    journal_report,
    jubilees_report,
    month_balances_report,
    night_hours_report,
    sick_days_report,
    vacation_days_report,
    year_bounds,
)

router = APIRouter(prefix="/hr/reports", tags=["reports"])

JOURNAL_COLUMNS = [
    ("Tag", 0.16, "L"),
    ("Buchung", 0.48, "L"),
    ("Ist", 0.12, "R"),
    ("Soll", 0.12, "R"),
    ("Konto", 0.12, "R"),
]
BALANCE_GROUPS = [("Name", 1), ("Zeitkonto", 3), ("Urlaub", 4), ("Krankheit", 3)]
BALANCE_COLUMNS = [
    ("Name", 0.16, "L"),
    ("Vormonat", 0.08, "R"),
    ("Monat", 0.08, "R"),
    ("Gesamt", 0.08, "R"),
    ("Vormonat", 0.07, "R"),
    ("Aktuell", 0.07, "R"),
    ("Gesamt", 0.07, "R"),
    ("inkl. Zukunft", 0.09, "R"),
    ("Vormonat", 0.07, "R"),
    ("Aktuell", 0.07, "R"),
    ("Gesamt", 0.08, "R"),
]


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


def _absence_export(kind: str, start: date, end: date, people: list[dict], want_pdf: bool, want_csv: bool):
    title = "Krankheitstage" if kind == "sick" else "Urlaubstage"
    slug = "krankheitstage" if kind == "sick" else "urlaubstage"
    year_label = f"Jahr {start.year}" if start.year == end.year else f"{start.year}–{end.year}"
    subtitle = f"{format_de_date(start)} – {format_de_date(end)} · {year_label}"
    if want_pdf:
        period_sum = sum(row["period_days"] for row in people)
        year_sum = sum(row["year_days"] for row in people)
        return _pdf_response(
            f"{slug}-{start.isoformat()}-{end.isoformat()}.pdf",
            table_pdf(
                title=title,
                subtitle=subtitle,
                org=_org(),
                columns=[("Name", 0.5, "L"), ("Zeitraum", 0.25, "R"), ("Jahr", 0.25, "R")],
                rows=[[row["display_name"], str(row["period_days"]), str(row["year_days"])] for row in people],
                totals=["Summe", str(period_sum), str(year_sum)] if people else None,
            ),
        )
    if want_csv:
        return _csv_response(
            f"{slug}-{start.isoformat()}-{end.isoformat()}.csv",
            ["Name", "Zeitraum", "Jahr"],
            [[row["display_name"], row["period_days"], row["year_days"]] for row in people],
        )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "year": start.year,
        "people": people,
    }


def _journal_account_rows(report: dict) -> list[list[str]]:
    accounts = report.get("accounts") or {}
    return [
        [
            "Zeitkonto",
            de_num(accounts.get("flex_prev") or 0, 1, signed=True),
            de_num(accounts.get("flex_month") or 0, 1, signed=True),
            "-",
            de_num(accounts.get("flex_total") or 0, 1, signed=True),
        ],
        [
            "Urlaubskonto",
            de_days(accounts.get("vacation_remaining_prev")),
            de_days(-(accounts.get("vacation_month") or 0), signed=True),
            de_days(accounts.get("vacation_planned") or 0),
            de_days(accounts.get("vacation_remaining")),
        ],
    ]


def _journal_table_rows(report: dict) -> list[list[str]]:
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
    return rows


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
    return _absence_export("sick", start, end, people, _want_pdf(request, format), _want_csv(request, format))


@router.get("/vacation-days")
@router.get("/vacation-days.csv")
@router.get("/vacation-days.pdf")
def vacation_days(
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
    people = vacation_days_report(db, start, end, _parse_user_ids(user_ids))
    return _absence_export("vacation", start, end, people, _want_pdf(request, format), _want_csv(request, format))


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
    subtitle = f"Stand {format_de_date(stichtag)} · {format_month_label(month)}"
    csv_headers = [
        "Name",
        "Zeitkonto Vormonat",
        "Zeitkonto Monat",
        "Zeitkonto Gesamt",
        "Urlaub Vormonat",
        "Urlaub aktuell",
        "Urlaub Gesamt",
        "Urlaub inkl. Zukunft",
        "Krankheit Vormonat",
        "Krankheit aktuell",
        "Krankheit Gesamt",
    ]
    csv_rows = [
        [
            row["display_name"],
            de_num(row["flex_prev"], 1, signed=True),
            de_num(row["flex_month"], 1, signed=True),
            de_num(row["flex_total"], 1, signed=True),
            row["vacation_prev"],
            row["vacation_month"],
            row["vacation_total"],
            row["vacation_future"],
            row["sick_prev"],
            row["sick_month"],
            row["sick_total"],
        ]
        for row in people
    ]
    if _want_pdf(request, format):
        totals = None
        if people:
            totals = [
                "Summe",
                de_num(sum(row["flex_prev"] for row in people), 1, signed=True),
                de_num(sum(row["flex_month"] for row in people), 1, signed=True),
                de_num(sum(row["flex_total"] for row in people), 1, signed=True),
                str(sum(row["vacation_prev"] for row in people)),
                str(sum(row["vacation_month"] for row in people)),
                str(sum(row["vacation_total"] for row in people)),
                str(sum(row["vacation_future"] for row in people)),
                str(sum(row["sick_prev"] for row in people)),
                str(sum(row["sick_month"] for row in people)),
                str(sum(row["sick_total"] for row in people)),
            ]
        return _pdf_response(
            f"salden-{month}-stichtag-{stichtag.isoformat()}.pdf",
            table_pdf(
                title="Monatssalden",
                subtitle=subtitle,
                org=_org(),
                landscape=True,
                note=VACATION_NOTE,
                groups=BALANCE_GROUPS,
                columns=BALANCE_COLUMNS,
                rows=[
                    [
                        row["display_name"],
                        de_num(row["flex_prev"], 1, signed=True),
                        de_num(row["flex_month"], 1, signed=True),
                        de_num(row["flex_total"], 1, signed=True),
                        str(row["vacation_prev"]),
                        str(row["vacation_month"]),
                        str(row["vacation_total"]),
                        str(row["vacation_future"]),
                        str(row["sick_prev"]),
                        str(row["sick_month"]),
                        str(row["sick_total"]),
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
                    ("Datum", 0.16, "L"),
                    ("Name", 0.32, "L"),
                    ("Art", 0.2, "L"),
                    ("Jahre", 0.1, "R"),
                    ("Geboren/Eintritt", 0.22, "L"),
                ],
                rows=[
                    [
                        de_date(row["date"]),
                        row["display_name"],
                        row["label"],
                        str(row["years"]),
                        de_date(row["origin_date"]) if row.get("origin_date") else "-",
                    ]
                    for row in events
                ],
            ),
        )
    if _want_csv(request, format):
        return _csv_response(
            f"jubilaeen-{year}-hj{half}.csv",
            ["Name", "Datum", "Art", "Jahre", "Geboren/Eintritt"],
            [
                [row["display_name"], row["date"], row["label"], row["years"], row.get("origin_date") or ""]
                for row in events
            ],
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
            f"lohnarten-{month}.pdf",
            table_pdf(
                title="Lohnarten",
                subtitle=subtitle,
                org=_org(),
                columns=[
                    ("Name", 0.32, "L"),
                    ("1 (20–24)", 0.17, "R"),
                    ("2 (0–4)", 0.17, "R"),
                    ("3 (4–6)", 0.17, "R"),
                    ("Summe aus 1 und 3", 0.17, "R"),
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
                note="Nachtfenster als Lohnarten 1–3 aus Stempelintervallen. Auto-Pause wird nicht abgezogen.",
            ),
        )
    if _want_csv(request, format):
        return _csv_response(
            f"lohnarten-{month}.csv",
            ["Name", "1 (20-24)", "2 (0-4)", "3 (4-6)", "Summe aus 1 und 3"],
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


@router.get("/journal")
@router.get("/journal.pdf")
def journal(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    user_id: int | None = Query(None),
    user_ids: str | None = Query(None),
):
    _actor(request, db)
    ids = _parse_user_ids(user_ids)
    if user_id is not None:
        ids = {user_id}
    people = journal_people(db, month, ids)
    if user_id is not None and not people:
        user = db.scalar(select(User).options(selectinload(User.work_model)).where(User.id == user_id))
        if not user:
            raise HTTPException(404, "Nicht gefunden")
        people = [user]
    reports = [journal_report(db, user, month) for user in people]
    if _want_pdf(request, None) or request.url.path.endswith(".pdf"):
        if not reports:
            raise HTTPException(400, "Keine Personen für das Journal")
        first = reports[0]
        pdf = ReportPDF(
            title=f"Journal {first['display_name']}",
            subtitle=first["month_label"],
            org=_org(),
        )
        pdf.table(JOURNAL_COLUMNS, _journal_table_rows(first), note="")
        pdf.accounts_table(_journal_account_rows(first), note=JOURNAL_ACCOUNT_NOTE)
        for report in reports[1:]:
            pdf.report_title = f"Journal {report['display_name']}"
            pdf.report_subtitle = report["month_label"]
            pdf.add_page()
            pdf.table(JOURNAL_COLUMNS, _journal_table_rows(report), note="")
            pdf.accounts_table(_journal_account_rows(report), note=JOURNAL_ACCOUNT_NOTE)
        filename = f"journale-{month}.pdf" if len(reports) != 1 else f"journal-{month}.pdf"
        return _pdf_response(filename, pdf.bytes())
    return {"month": month, "people": reports}
