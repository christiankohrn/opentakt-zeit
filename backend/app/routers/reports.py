from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import current_user, require_hr
from app.database import get_db
from app.models import User
from app.reports import jubilees_report, month_balances_report, night_hours_report, sick_days_report

router = APIRouter(prefix="/hr/reports", tags=["reports"])


def _actor(request: Request, db: Session) -> User:
    return require_hr(current_user(request, db))


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


def _de_num(value: float) -> str:
    return str(value).replace(".", ",")


def _want_csv(fmt: str | None) -> bool:
    return (fmt or "").lower() == "csv"


@router.get("/sick-days")
@router.get("/sick-days.csv")
def sick_days(
    request: Request,
    db: Session = Depends(get_db),
    year: int = Query(..., ge=1990, le=2100),
    format: str | None = Query(None, alias="format"),
):
    _actor(request, db)
    people = sick_days_report(db, year)
    if _want_csv(format) or request.url.path.endswith(".csv"):
        return _csv_response(
            f"krankheitstage-{year}.csv",
            ["Name", "Krankheitstage"],
            [[row["display_name"], row["sick_days"]] for row in people],
        )
    return {"year": year, "people": people}


@router.get("/month-balances")
@router.get("/month-balances.csv")
def month_balances(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    format: str | None = Query(None, alias="format"),
):
    _actor(request, db)
    people = month_balances_report(db, month)
    if _want_csv(format) or request.url.path.endswith(".csv"):
        return _csv_response(
            f"salden-{month}.csv",
            ["Name", "Ist", "Soll", "Konto Monat", "Krankheitstage", "Urlaubstage"],
            [
                [
                    row["display_name"],
                    _de_num(row["work_hours"]),
                    _de_num(row["soll_hours"]),
                    _de_num(row["delta_hours"]),
                    row["sick_days"],
                    row["vacation_days"],
                ]
                for row in people
            ],
        )
    return {"month": month, "people": people}


@router.get("/jubilees")
@router.get("/jubilees.csv")
def jubilees(
    request: Request,
    db: Session = Depends(get_db),
    year: int = Query(..., ge=1990, le=2100),
    half: int = Query(..., ge=1, le=2),
    format: str | None = Query(None, alias="format"),
):
    _actor(request, db)
    events = jubilees_report(db, year, half)
    if _want_csv(format) or request.url.path.endswith(".csv"):
        return _csv_response(
            f"jubilaeen-{year}-hj{half}.csv",
            ["Name", "Datum", "Art", "Jahre"],
            [[row["display_name"], row["date"], row["label"], row["years"]] for row in events],
        )
    return {"year": year, "half": half, "events": events}


@router.get("/night-hours")
@router.get("/night-hours.csv")
def night_hours(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    format: str | None = Query(None, alias="format"),
):
    _actor(request, db)
    people = night_hours_report(db, month)
    if _want_csv(format) or request.url.path.endswith(".csv"):
        return _csv_response(
            f"nachtstunden-{month}.csv",
            ["Name", "20-24", "0-4", "4-6", "1+3"],
            [
                [
                    row["display_name"],
                    _de_num(row["hours_20_24"]),
                    _de_num(row["hours_0_4"]),
                    _de_num(row["hours_4_6"]),
                    _de_num(row["hours_1_plus_3"]),
                ]
                for row in people
            ],
        )
    return {"month": month, "people": people}
