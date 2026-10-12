from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.models import Punch
from app.reports import absence_counts, jubilees_report, month_balances_report
from app.timecalc import work_intervals


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def users_by_name(client) -> dict:
    res = client.get("/api/hr/users")
    assert res.status_code == 200, res.text
    return {u["username"]: u for u in res.json()}


def model_id(client) -> int:
    models = client.get("/api/hr/work-models").json()
    return models[0]["id"]


def create_person(client, username: str, display_name: str, **extra):
    body = {
        "username": username,
        "display_name": display_name,
        "role": "employee",
        "work_model_id": model_id(client),
        "web_login": False,
        **extra,
    }
    res = client.post("/api/hr/users", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def assert_pdf(res):
    assert res.status_code == 200, res.text
    assert res.content.startswith(b"%PDF")
    assert "pdf" in res.headers["content-type"]
    assert len(res.content) > 400


def pdf_page_count(content: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", content))


def test_employee_cannot_read_reports(client):
    login(client)
    create_person(
        client,
        "report-emp",
        "Report Emp",
        web_login=True,
        password="Geheim-99x",
    )
    client.post("/api/auth/logout")
    login(client, "report-emp", "Geheim-99x")
    res = client.get("/api/hr/reports/sick-days?year=2026")
    assert res.status_code == 403
    pdf = client.get("/api/hr/reports/sick-days.pdf?year=2026")
    assert pdf.status_code == 403


def test_sick_days_includes_zeros_and_skips_unemployed(client):
    login(client)
    sick = create_person(client, "krank-anna", "Krank, Anna", hired_on="2025-01-01")
    zero = create_person(client, "gesund-ben", "Gesund, Ben", hired_on="2025-01-01")
    create_person(client, "alina-alt", "Alt, Alina", hired_on="2020-01-01", left_on="2025-06-01")
    create_person(client, "zara-neu", "Zukunft, Zara", hired_on="2027-01-01")
    added = client.post(
        f"/api/hr/users/{sick['id']}/absences",
        json={"kind": "sick", "start": "2026-03-02", "end": "2026-03-04"},
    )
    assert added.status_code == 200, added.text
    january = client.post(
        f"/api/hr/users/{sick['id']}/absences",
        json={"kind": "sick", "start": "2026-01-08", "end": "2026-01-08"},
    )
    assert january.status_code == 200, january.text
    res = client.get("/api/hr/reports/sick-days?year=2026")
    assert res.status_code == 200, res.text
    by_name = {row["display_name"]: row for row in res.json()["people"]}
    assert by_name["Krank, Anna"]["period_days"] == 4
    assert by_name["Krank, Anna"]["year_days"] == 4
    assert by_name["Krank, Anna"]["sick_days"] == 4
    assert by_name["Gesund, Ben"]["period_days"] == 0
    assert by_name["Gesund, Ben"]["year_days"] == 0
    assert "Alt, Alina" not in by_name
    assert "Zukunft, Zara" not in by_name
    csv_res = client.get("/api/hr/reports/sick-days.csv?year=2026")
    assert csv_res.status_code == 200
    text = csv_res.text
    assert "Zeitraum" in text
    assert "Krank, Anna;4;4" in text
    assert zero["id"]

    filtered = client.get(
        f"/api/hr/reports/sick-days?from=2026-03-01&to=2026-03-31&user_ids={sick['id']}"
    )
    assert filtered.status_code == 200, filtered.text
    names = [row["display_name"] for row in filtered.json()["people"]]
    assert names == ["Krank, Anna"]
    assert filtered.json()["people"][0]["period_days"] == 3
    assert filtered.json()["people"][0]["year_days"] == 4

    empty = client.get("/api/hr/reports/sick-days?from=2026-01-01&to=2026-12-31&user_ids=")
    assert empty.status_code == 200
    assert empty.json()["people"] == []
    assert_pdf(client.get("/api/hr/reports/sick-days.pdf?from=2026-01-01&to=2026-12-31"))


def test_vacation_days_period_and_year(client):
    login(client)
    person = create_person(client, "urlaub-eva", "Eva Urlaub", hired_on="2025-01-01")
    booked = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "vacation", "start": "2026-02-02", "end": "2026-02-03"},
    )
    assert booked.status_code == 200, booked.text
    later = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "vacation", "start": "2026-08-10", "end": "2026-08-10"},
    )
    assert later.status_code == 200, later.text
    res = client.get(
        f"/api/hr/reports/vacation-days?from=2026-02-01&to=2026-02-28&user_ids={person['id']}"
    )
    assert res.status_code == 200, res.text
    row = res.json()["people"][0]
    assert row["period_days"] == 2
    assert row["year_days"] == 3
    csv_res = client.get("/api/hr/reports/vacation-days.csv?year=2026")
    assert csv_res.status_code == 200
    assert "Urlaub, Eva;3;3" in csv_res.text
    assert_pdf(client.get("/api/hr/reports/vacation-days.pdf?year=2026"))


def test_vacation_weekends_consume_no_quota(client):
    login(client)
    person = create_person(
        client, "urlaub-willi", "Willi Urlaub", hired_on="2025-01-01", vacation_days_year=30
    )
    booked = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "vacation", "start": "2026-03-02", "end": "2026-03-08"},
    )
    assert booked.status_code == 200, booked.text
    res = client.get(
        f"/api/hr/reports/vacation-days?from=2026-03-01&to=2026-03-31&user_ids={person['id']}"
    )
    assert res.status_code == 200, res.text
    row = res.json()["people"][0]
    assert row["period_days"] == 5
    assert row["year_days"] == 5
    journal = client.get(f"/api/hr/reports/journal?month=2026-03&user_ids={person['id']}")
    assert journal.status_code == 200, journal.text
    accounts = journal.json()["people"][0]["accounts"]
    assert accounts["vacation_month"] == 5
    assert accounts["vacation_remaining"] == 25


def test_month_balances_count_future_vacation(client):
    login(client)
    person = create_person(client, "urlaub-clara", "Clara Urlaub", hired_on="2025-01-01")
    booked = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "vacation", "start": "2026-09-28", "end": "2026-09-28"},
    )
    assert booked.status_code == 200, booked.text
    sick = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "sick", "start": "2026-09-03", "end": "2026-09-03"},
    )
    assert sick.status_code == 200, sick.text
    earlier = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "vacation", "start": "2026-04-02", "end": "2026-04-02"},
    )
    assert earlier.status_code == 200, earlier.text
    db = SessionLocal()
    try:
        rows = month_balances_report(db, "2026-09", as_of=date(2026, 9, 15), today=date(2026, 9, 15))
    finally:
        db.close()
    clara = next(row for row in rows if row["user_id"] == person["id"])
    assert clara["vacation_prev"] == 1
    assert clara["vacation_month"] == 0
    assert clara["vacation_total"] == 1
    assert clara["vacation_future"] == 2
    assert clara["sick_prev"] == 0
    assert clara["sick_month"] == 1
    assert clara["sick_total"] == 1
    http = client.get("/api/hr/reports/month-balances?month=2026-09&as_of=2026-09-15")
    assert http.status_code == 200
    found = next(row for row in http.json()["people"] if row["user_id"] == person["id"])
    assert found["vacation_prev"] == 1
    assert found["vacation_future"] == 2
    assert found["sick_month"] == 1
    assert isinstance(found["flex_prev"], (int, float))
    assert isinstance(found["flex_total"], (int, float))
    assert "inkl. Zukunft" in http.json()["note"]
    csv_res = client.get("/api/hr/reports/month-balances.csv?month=2026-09&as_of=2026-09-15")
    assert "Zeitkonto Vormonat" in csv_res.text
    assert "Urlaub inkl. Zukunft" in csv_res.text
    assert_pdf(client.get("/api/hr/reports/month-balances.pdf?month=2026-09&as_of=2026-09-15"))

    db = SessionLocal()
    try:
        later = month_balances_report(db, "2026-09", as_of=date(2026, 9, 30), today=date(2026, 9, 15))
    finally:
        db.close()
    clara_later = next(row for row in later if row["user_id"] == person["id"])
    assert clara_later["vacation_month"] == 1
    assert clara_later["vacation_total"] == 2
    assert clara_later["vacation_future"] == 2


def test_jubilees_birthday_and_ten_year(client):
    login(client)
    person = create_person(
        client,
        "jubi-dana",
        "Dana Jubiläum",
        hired_on="2016-09-01",
        birthday="1990-03-12",
    )
    none = create_person(client, "ohne-geburt", "Otto Ohne", hired_on="2016-09-01")
    hj1 = client.get("/api/hr/reports/jubilees?year=2026&half=1")
    assert hj1.status_code == 200, hj1.text
    events = hj1.json()["events"]
    birthday = next(row for row in events if row["user_id"] == person["id"] and row["kind"] == "birthday")
    assert birthday["date"] == "2026-03-12"
    assert birthday["origin_date"] == "1990-03-12"
    assert birthday["years"] == 36
    assert not any(row["user_id"] == none["id"] and row["kind"] == "birthday" for row in events)

    hj2 = client.get("/api/hr/reports/jubilees?year=2026&half=2")
    assert hj2.status_code == 200, hj2.text
    later = hj2.json()["events"]
    assert not any(row["user_id"] == person["id"] and row["kind"] == "birthday" for row in later)
    ten = next(row for row in later if row["user_id"] == person["id"] and row["kind"] == "jubilee_10")
    assert ten["date"] == "2026-09-01"
    assert ten["origin_date"] == "2016-09-01"
    assert ten["years"] == 10
    hire = next(row for row in later if row["user_id"] == person["id"] and row["kind"] == "hire")
    assert hire["date"] == "2026-09-01"
    assert hire["origin_date"] == "2016-09-01"
    assert hire["years"] == 10
    db = SessionLocal()
    try:
        rows = jubilees_report(db, 2026, 2)
    finally:
        db.close()
    assert any(row["kind"] == "jubilee_10" and row["user_id"] == person["id"] for row in rows)
    csv_res = client.get("/api/hr/reports/jubilees.csv?year=2026&half=2")
    assert "Geboren/Eintritt" in csv_res.text
    assert_pdf(client.get("/api/hr/reports/jubilees.pdf?year=2026&half=2"))


def test_night_hours_overnight_shift(client):
    login(client)
    people = users_by_name(client)
    erika = people["erika"]
    hired = client.patch(f"/api/hr/users/{erika['id']}/account", json={"hired_on": "2026-01-01"})
    assert hired.status_code == 200, hired.text
    first = client.put(
        f"/api/hr/users/{erika['id']}/days/2026-08-07",
        json={"reason": "Nachtschicht anlegen", "punches": [{"kind": "in", "time": "22:00"}]},
    )
    assert first.status_code == 200, first.text
    second = client.put(
        f"/api/hr/users/{erika['id']}/days/2026-08-08",
        json={"reason": "Nachtschicht anlegen", "punches": [{"kind": "out", "time": "06:00"}]},
    )
    assert second.status_code == 200, second.text
    res = client.get("/api/hr/reports/night-hours?month=2026-08")
    assert res.status_code == 200, res.text
    row = next(item for item in res.json()["people"] if item["user_id"] == erika["id"])
    assert abs(row["hours_20_24"] - 2.0) < 0.05
    assert abs(row["hours_0_4"] - 4.0) < 0.05
    assert abs(row["hours_4_6"] - 2.0) < 0.05
    assert abs(row["hours_1_plus_3"] - 4.0) < 0.05
    csv_res = client.get("/api/hr/reports/night-hours.csv?month=2026-08")
    assert csv_res.status_code == 200
    assert "Summe aus 1 und 3" in csv_res.text
    assert "1 (20-24)" in csv_res.text
    pdf = client.get("/api/hr/reports/night-hours.pdf?month=2026-08")
    assert_pdf(pdf)
    assert b"lohnarten" in pdf.headers["content-disposition"].encode() or "lohnarten" in pdf.headers["content-disposition"]


def test_journals_batch_pdf(client):
    login(client)
    people = users_by_name(client)
    erika = people["erika"]
    maxx = people["mitarbeiter"]
    for person in (erika, maxx):
        patched = client.patch(f"/api/hr/users/{person['id']}/account", json={"hired_on": "2026-01-01"})
        assert patched.status_code == 200, patched.text
    listing = client.get("/api/hr/reports/journal?month=2026-08")
    assert listing.status_code == 200, listing.text
    names = [row["display_name"] for row in listing.json()["people"]]
    assert len(names) >= 2
    assert "accounts" in listing.json()["people"][0]
    assert "flex_total" in listing.json()["people"][0]["accounts"]
    selected = client.get(
        f"/api/hr/reports/journal.pdf?month=2026-08&user_ids={erika['id']},{maxx['id']}"
    )
    assert_pdf(selected)
    assert "journale-2026-08.pdf" in selected.headers["content-disposition"]
    assert pdf_page_count(selected.content) == 2
    everyone = client.get("/api/hr/reports/journal.pdf?month=2026-08")
    assert_pdf(everyone)
    assert pdf_page_count(everyone.content) == len(names)
    empty = client.get("/api/hr/reports/journal.pdf?month=2026-08&user_ids=")
    assert empty.status_code == 400
    one = client.get(f"/api/hr/reports/journal.pdf?user_id={erika['id']}&month=2026-08")
    assert_pdf(one)
    assert "journal-2026-08.pdf" in one.headers["content-disposition"]
    assert pdf_page_count(one.content) == 1


def test_journal_accounts_resturlaub_and_planned(client):
    login(client)
    person = create_person(
        client,
        "konto-finn",
        "Finn Konto",
        hired_on="2025-01-01",
        vacation_days_year=30,
    )
    earlier = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "vacation", "start": "2026-02-02", "end": "2026-02-03"},
    )
    assert earlier.status_code == 200, earlier.text
    current = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "vacation", "start": "2026-08-10", "end": "2026-08-10"},
    )
    assert current.status_code == 200, current.text
    later = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "vacation", "start": "2026-09-28", "end": "2026-09-28"},
    )
    assert later.status_code == 200, later.text
    res = client.get(f"/api/hr/reports/journal?month=2026-08&user_ids={person['id']}")
    assert res.status_code == 200, res.text
    accounts = res.json()["people"][0]["accounts"]
    assert accounts["vacation_month"] == 1
    assert accounts["vacation_planned"] == 1
    assert accounts["vacation_remaining_prev"] == 28
    assert accounts["vacation_remaining"] == 26
    assert accounts["vacation_allowance"] == 30
    none = create_person(client, "ohne-anspruch", "Ohne Anspruch", hired_on="2025-01-01")
    empty = client.get(f"/api/hr/reports/journal?month=2026-08&user_ids={none['id']}")
    assert empty.status_code == 200, empty.text
    missing = empty.json()["people"][0]["accounts"]
    assert missing["vacation_remaining"] is None
    assert missing["vacation_remaining_prev"] is None
    pdf = client.get(f"/api/hr/reports/journal.pdf?month=2026-08&user_ids={person['id']}")
    assert_pdf(pdf)
    assert pdf_page_count(pdf.content) == 1


def test_journal_account_matches_the_month_row_to_the_minute(client):
    from app.balance import format_hm

    login(client)
    person = create_person(
        client,
        "minute-konto",
        "Minute Konto",
        hired_on="2026-08-03",
        left_on="2026-08-03",
    )
    account = client.patch(
        f"/api/hr/users/{person['id']}/account",
        json={"opening_balance_hours": -4.2, "opening_balance_on": "2026-07-31"},
    )
    assert account.status_code == 200, account.text
    stored = client.put(
        f"/api/hr/users/{person['id']}/days/2026-08-03",
        json={"reason": "Testtag", "punches": [{"kind": "in", "time": "08:00"}, {"kind": "out", "time": "16:28"}]},
    )
    assert stored.status_code == 200, stored.text
    res = client.get(f"/api/hr/reports/journal?month=2026-08&user_ids={person['id']}")
    assert res.status_code == 200, res.text
    report = res.json()["people"][0]
    month = next(row for row in report["rows"] if row["type"] == "month")
    accounts = report["accounts"]
    assert format_hm(month["delta_hours"], signed=True) == "-0:02"
    assert format_hm(accounts["flex_month"], signed=True) == "-0:02"
    assert format_hm(accounts["flex_prev"], signed=True) == "-4:12"
    assert format_hm(accounts["flex_total"], signed=True) == "-4:14"
    from app.pdf import ReportPDF

    pdf = ReportPDF(title="Journal Probe", subtitle="August 2026", org="Org")
    columns = [
        ("Tag", 0.16, "L"),
        ("Buchung", 0.48, "L"),
        ("Ist", 0.12, "R"),
        ("Soll", 0.12, "R"),
        ("Konto", 0.12, "R"),
    ]
    booking = "Kommen 08:00 · Pause Beginn 12:00 · Pause Ende 12:30 · Gehen 16:30"
    rows = [[f"{day:02d}.08.", booking, "8:00", "8:00", "0:00"] for day in range(1, 32)]
    rows.extend([["Woche", "", "40:00", "40:00", "0:00"] for _ in range(6)])
    rows.append(["Monat", "", "176:00", "176:00", "0:00"])
    accounts = [
        ["Zeitkonto", "+1:00", "+2:00", "-", "+3:00"],
        ["Urlaubskonto", "27", "0", "3", "24"],
    ]
    pdf.journal_person(columns, rows, accounts, note="Resturlaub = Jahresanspruch - genommen - verplant.")
    assert pdf_page_count(pdf.bytes()) == 1


def test_journal_month_row_matches_flex_in_current_month(client):
    login(client)
    person = create_person(client, "journal-karla", "Karla Journal", hired_on="2026-01-01")
    today = date.today()
    month = f"{today.year}-{today.month:02d}"
    res = client.get(f"/api/hr/reports/journal?month={month}&user_id={person['id']}")
    assert res.status_code == 200, res.text
    report = res.json()["people"][0]
    month_row = next(row for row in report["rows"] if row["type"] == "month")
    assert month_row["delta_hours"] == report["accounts"]["flex_month"]


def test_csv_neutralizes_formula_cells(client):
    from app.reports import safe_csv_cell

    assert safe_csv_cell("=1+1") == "'=1+1"
    assert safe_csv_cell("+2+2") == "'+2+2"
    assert safe_csv_cell("-2+2") == "'-2+2"
    assert safe_csv_cell("@SUM(A1)") == "'@SUM(A1)"
    assert safe_csv_cell("Normal, Name") == "Normal, Name"
    assert safe_csv_cell(4) == 4
    login(client)
    person = create_person(client, "formel-fritz", "=1+1")
    res = client.get("/api/hr/reports/sick-days.csv?year=2026")
    assert res.status_code == 200, res.text
    assert "'=1+1;" in res.text
    assert "\n=1+1;" not in res.text
    booked = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "vacation", "start": "2026-03-02", "end": "2026-03-02"},
    )
    assert booked.status_code == 200, booked.text
    export = client.get(f"/api/hr/export.csv?month=2026-03&user_id={person['id']}")
    assert export.status_code == 200, export.text
    assert "'=1+1;" in export.text
    assert "\n=1+1;" not in export.text


def test_manual_bookings_move_time_and_vacation_accounts(client):
    from app.balance import format_hm

    login(client)
    person = create_person(client, "auszahlung", "Auszahlung", hired_on="2026-08-03", left_on="2026-08-03")
    opening = client.patch(
        f"/api/hr/users/{person['id']}/account",
        json={"opening_balance_hours": 0, "opening_balance_on": "2026-08-03"},
    )
    assert opening.status_code == 200, opening.text
    early = client.post(
        f"/api/hr/users/{person['id']}/ledger",
        json={"kind": "time", "day": "2026-08-02", "amount": -10, "reason": "vor dem Start"},
    )
    assert early.status_code == 200, early.text
    payout = client.post(
        f"/api/hr/users/{person['id']}/ledger",
        json={"kind": "time", "day": "2026-08-03", "amount": -35, "reason": "Auszahlung"},
    )
    assert payout.status_code == 200, payout.text
    days = client.get(f"/api/hr/users/{person['id']}/days?month=2026-08")
    assert days.status_code == 200, days.text
    body = days.json()
    worked = sum(float(day["delta_hours"] or 0) for day in body["days"] if day["date"] == "2026-08-03")
    assert format_hm(body["month_flex"]) == format_hm(worked - 35)
    journal = client.get(f"/api/hr/reports/journal?month=2026-08&user_ids={person['id']}")
    assert journal.status_code == 200, journal.text
    report = journal.json()["people"][0]
    month = next(row for row in report["rows"] if row["type"] == "month")
    assert format_hm(month["delta_hours"]) == format_hm(worked - 35)
    assert format_hm(report["accounts"]["flex_month"]) == format_hm(worked - 35)
    ledger = client.get(f"/api/hr/users/{person['id']}/ledger?year=2026")
    assert ledger.status_code == 200, ledger.text
    reasons = [row["reason"] for row in ledger.json()["time_entries"]]
    assert reasons == ["vor dem Start", "Auszahlung"]

    holiday = create_person(client, "urlaub-buchung", "Urlaub Buchung", hired_on="2025-01-01", vacation_days_year=30)
    added = client.post(
        f"/api/hr/users/{holiday['id']}/absences",
        json={"kind": "vacation", "start": "2026-08-10", "end": "2026-08-10"},
    )
    assert added.status_code == 200, added.text
    correction = client.post(
        f"/api/hr/users/{holiday['id']}/ledger",
        json={"kind": "vacation", "day": "2026-08-01", "amount": -2, "reason": "Korrektur"},
    )
    assert correction.status_code == 200, correction.text
    accounts = client.get(f"/api/hr/reports/journal?month=2026-08&user_ids={holiday['id']}")
    assert accounts.status_code == 200, accounts.text
    vacation = accounts.json()["people"][0]["accounts"]
    assert vacation["vacation_remaining_prev"] == 30
    assert vacation["vacation_remaining"] == 27
    book = client.get(f"/api/hr/users/{holiday['id']}/ledger?year=2026")
    assert book.status_code == 200, book.text
    shown = book.json()
    assert shown["vacation_allowance"] == 30
    assert shown["vacation_remaining"] == 27
    assert len(shown["vacation_days"]) == 1


def test_work_intervals_split_overnight():
    punches = [
        Punch(
            user_id=1,
            kind="in",
            server_time=datetime(2026, 8, 7, 22, 0, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(ZoneInfo("UTC")),
            source="test",
        ),
        Punch(
            user_id=1,
            kind="out",
            server_time=datetime(2026, 8, 8, 6, 0, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(ZoneInfo("UTC")),
            source="test",
        ),
    ]
    now = datetime(2026, 8, 9, tzinfo=ZoneInfo("UTC"))
    night = work_intervals(punches, date(2026, 8, 7), now=now)
    morning = work_intervals(punches, date(2026, 8, 8), now=now)
    night_hours = sum((b - a).total_seconds() for a, b in night) / 3600
    morning_hours = sum((b - a).total_seconds() for a, b in morning) / 3600
    assert abs(night_hours - 2.0) < 0.05
    assert abs(morning_hours - 6.0) < 0.05


def test_school_and_future_comp_time_can_be_booked(client):
    login(client)
    person = users_by_name(client)["mitarbeiter"]
    comp_day = "2027-01-13"
    school_day = "2027-01-14"
    try:
        comp = client.post(
            f"/api/hr/users/{person['id']}/absences",
            json={"kind": "comp_time", "start": comp_day, "end": comp_day},
        )
        assert comp.status_code == 200, comp.text
        school = client.post(
            f"/api/hr/users/{person['id']}/absences",
            json={"kind": "school", "start": school_day, "end": school_day},
        )
        assert school.status_code == 200, school.text
        days = client.get(f"/api/hr/users/{person['id']}/days?month=2027-01").json()["days"]
        comp_row = next(row for row in days if row["date"] == comp_day)
        school_row = next(row for row in days if row["date"] == school_day)
        assert comp_row["absence"]["kind"] == "comp_time"
        assert comp_row["delta_hours"] < 0
        assert comp_row["warnings"] == []
        assert school_row["absence"]["kind"] == "school"
        assert school_row["delta_hours"] == 0
    finally:
        client.delete(f"/api/hr/users/{person['id']}/absences/{comp_day}")
        client.delete(f"/api/hr/users/{person['id']}/absences/{school_day}")


def _book(client, user_id: int, kind: str, day: str) -> None:
    res = client.post(
        f"/api/hr/users/{user_id}/absences",
        json={"kind": kind, "start": day, "end": day},
    )
    assert res.status_code == 200, res.text


def test_absence_counts_match_day_summaries(client):
    from sqlalchemy import delete, select

    from app.balance import days_in_range, is_employed
    from app.models import DayModel, User, WorkModel

    login(client)
    person = create_person(
        client, "ae-count", "Count Ab", hired_on="2025-06-01", left_on="2026-06-30", vacation_days_year=30
    )
    uid = person["id"]
    zero_id: int | None = None
    try:
        _book(client, uid, "vacation", "2026-02-10")
        _book(client, uid, "vacation", "2026-03-10")
        _book(client, uid, "vacation", "2026-05-05")
        _book(client, uid, "vacation", "2026-03-14")  # Samstag zählt nicht
        _book(client, uid, "vacation", "2026-04-03")  # Karfreitag zählt nicht
        _book(client, uid, "vacation", "2026-07-07")  # nach Austritt zählt nicht
        _book(client, uid, "sick", "2026-02-11")
        _book(client, uid, "sick", "2026-03-08")  # Sonntag zählt bei Krankheit mit
        created = client.post(
            "/api/hr/work-models",
            json={
                "name": "Nullmodell-Zähltest",
                "hours_mon": 0,
                "hours_tue": 0,
                "hours_wed": 0,
                "hours_thu": 0,
                "hours_fri": 0,
                "hours_sat": 0,
                "hours_sun": 0,
            },
        )
        assert created.status_code == 200, created.text
        zero_id = created.json()["id"]
        zero_model = client.put(f"/api/hr/users/{uid}/days/2026-03-11/model", json={"work_model_id": zero_id})
        assert zero_model.status_code == 200, zero_model.text
        _book(client, uid, "vacation", "2026-03-11")  # Tag ohne Soll zählt nicht

        year_start, year_end = date(2026, 1, 1), date(2026, 12, 31)
        prev_last, as_of = date(2026, 2, 28), date(2026, 3, 15)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.id == uid))
            assert user is not None
            # Alte Zähllogik über Tagessummen als Referenz.
            vac_prev = vac_ytd = vac_year = 0
            sick_prev = sick_ytd = 0
            for summary in days_in_range(db, user, year_start, year_end):
                day = date.fromisoformat(str(summary["date"]))
                kind = ((summary.get("absence") or {}) or {}).get("kind") or ""
                if not is_employed(user, day) or day < year_start or day > year_end:
                    continue
                if kind == "vacation" and float(summary.get("soll_hours") or 0) <= 0:
                    continue
                if kind == "vacation":
                    vac_year += 1
                    if day <= prev_last:
                        vac_prev += 1
                    if day <= as_of:
                        vac_ytd += 1
                elif kind == "sick":
                    if day <= prev_last:
                        sick_prev += 1
                    if day <= as_of:
                        sick_ytd += 1
            expected = (vac_prev, vac_ytd, vac_year, sick_prev, sick_ytd)
            assert expected == (1, 2, 3, 1, 2)
            assert absence_counts(db, user, year_start, year_end, prev_last, as_of) == expected
            rows = month_balances_report(db, "2026-03", as_of=as_of, today=as_of)
        finally:
            db.close()
        clara = next(row for row in rows if row["user_id"] == uid)
        assert (clara["vacation_prev"], clara["vacation_total"], clara["vacation_future"]) == (1, 2, 3)
        assert (clara["sick_prev"], clara["sick_total"]) == (1, 2)
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(DayModel).where(DayModel.user_id == uid))
            if zero_id is not None:
                db.execute(delete(WorkModel).where(WorkModel.id == zero_id))
            db.commit()
        finally:
            db.close()
