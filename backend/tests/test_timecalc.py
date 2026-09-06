from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.models import Punch
from app.timecalc import model_on_day, status_from_punches, summarize_day


def _p(kind: str, hour: int, minute: int = 0) -> Punch:
    t = datetime(2026, 9, 4, hour, minute, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(ZoneInfo("UTC"))
    return Punch(user_id=1, kind=kind, server_time=t, source="test")


def _p_on(day: date, kind: str, hour: int, minute: int = 0) -> Punch:
    t = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(
        ZoneInfo("UTC")
    )
    return Punch(user_id=1, kind=kind, server_time=t, source="test")


def test_status_machine():
    assert status_from_punches([]) == "away"
    assert status_from_punches([_p("in", 8)]) == "in"
    assert status_from_punches([_p("in", 8), _p("break_start", 12)]) == "break"
    assert status_from_punches([_p("in", 8), _p("break_start", 12), _p("break_end", 12, 30)]) == "in"
    assert status_from_punches([_p("in", 8), _p("out", 16)]) == "away"


def test_summarize_with_break():
    punches = [_p("in", 8), _p("break_start", 12), _p("break_end", 12, 30), _p("out", 16, 30)]
    day = summarize_day(punches, date(2026, 9, 4), None, now=datetime(2026, 9, 4, 20, tzinfo=ZoneInfo("UTC")))
    assert day["first_in"] == "08:00"
    assert day["last_out"] == "16:30"
    assert abs(day["work_hours"] - 8.0) < 0.05
    assert abs(day["break_hours"] - 0.5) < 0.05
    assert "break_short" not in day["warnings"]


def test_vacation_covers_soll():
    absence = SimpleNamespace(kind="vacation", note="Urlaub")
    day = summarize_day([], date(2026, 8, 5), None, now=datetime(2026, 8, 6, tzinfo=ZoneInfo("UTC")), absence=absence)
    assert day["delta_hours"] == 0
    assert day["absence"]["kind"] == "vacation"
    assert day["warnings"] == []


def test_overnight_shift_split_across_midnight():
    punches = [
        _p_on(date(2026, 8, 7), "in", 22, 0),
        _p_on(date(2026, 8, 8), "out", 6, 0),
    ]
    now = datetime(2026, 8, 9, tzinfo=ZoneInfo("UTC"))
    night = summarize_day(punches, date(2026, 8, 7), None, now=now)
    morning = summarize_day(punches, date(2026, 8, 8), None, now=now)
    assert "overnight" in night["warnings"]
    assert "checkout_missing" not in night["warnings"]
    assert abs(night["work_hours"] - 2.0) < 0.05
    assert abs(morning["work_hours"] - 6.0) < 0.05
    assert morning["last_out"] == "06:00"


def test_forgotten_checkout_not_overnight_when_next_day_starts_anew():
    punches = [
        _p_on(date(2026, 8, 24), "in", 14, 0),
        _p_on(date(2026, 8, 25), "in", 6, 0),
        _p_on(date(2026, 8, 25), "out", 14, 0),
    ]
    now = datetime(2026, 8, 26, tzinfo=ZoneInfo("UTC"))
    forgotten = summarize_day(punches, date(2026, 8, 24), None, now=now)
    assert "checkout_missing" in forgotten["warnings"]
    assert "overnight" not in forgotten["warnings"]


def test_missing_workday_without_booking():
    model = SimpleNamespace(
        hours_mon=8,
        hours_tue=8,
        hours_wed=8,
        hours_thu=8,
        hours_fri=8,
        hours_sat=0,
        hours_sun=0,
    )
    now = datetime(2026, 8, 18, tzinfo=ZoneInfo("UTC"))
    monday = summarize_day([], date(2026, 8, 17), model, now=now)
    sunday = summarize_day([], date(2026, 8, 16), model, now=now)
    assert "missing_day" in monday["warnings"]
    assert "missing_day" not in sunday["warnings"]


def test_calendar_holiday_skips_missing_day():
    model = SimpleNamespace(
        hours_mon=8,
        hours_tue=8,
        hours_wed=8,
        hours_thu=8,
        hours_fri=8,
        hours_sat=0,
        hours_sun=0,
    )
    cal = SimpleNamespace(kind="holiday", name="Testtag", source="law")
    day = summarize_day(
        [], date(2026, 8, 17), model, now=datetime(2026, 8, 18, tzinfo=ZoneInfo("UTC")), calendar=cal
    )
    assert "missing_day" not in day["warnings"]
    assert day["calendar"]["name"] == "Testtag"
    assert day["soll_hours"] == 0
    assert day["delta_hours"] == 0


def test_auto_break_deducts_when_none_stamped():
    punches = [_p("in", 8), _p("out", 16, 30)]
    now = datetime(2026, 9, 4, 20, tzinfo=ZoneInfo("UTC"))
    raw = summarize_day(punches, date(2026, 9, 4), None, now=now, auto_break=False)
    auto = summarize_day(punches, date(2026, 9, 4), None, now=now, auto_break=True)
    assert "break_short" in raw["warnings"]
    assert "break_short" not in auto["warnings"]
    assert auto["auto_break_minutes"] == 30
    assert abs(auto["work_hours"] - (raw["work_hours"] - 0.5)) < 0.05


def test_auto_break_skips_if_break_stamped():
    punches = [_p("in", 8), _p("break_start", 12), _p("break_end", 12, 30), _p("out", 16, 30)]
    day = summarize_day(
        punches, date(2026, 9, 4), None, now=datetime(2026, 9, 4, 20, tzinfo=ZoneInfo("UTC")), auto_break=True
    )
    assert day["auto_break_minutes"] == 0
    assert abs(day["break_hours"] - 0.5) < 0.05


def test_model_on_day_picks_latest_valid():
    full = SimpleNamespace(hours_mon=8)
    part = SimpleNamespace(hours_mon=4)
    timeline = [(date(2000, 1, 1), full), (date(2026, 9, 1), part)]
    assert model_on_day(timeline, date(2026, 8, 15), None) is full
    assert model_on_day(timeline, date(2026, 9, 1), None) is part
    assert model_on_day(timeline, date(2026, 10, 1), None) is part
    assert model_on_day([], date(2026, 9, 1), full) is full


def test_model_on_day_retroactive_changes_soll():
    full = SimpleNamespace(hours_mon=8, hours_tue=8, hours_wed=8, hours_thu=8, hours_fri=8, hours_sat=0, hours_sun=0)
    part = SimpleNamespace(hours_mon=4, hours_tue=4, hours_wed=4, hours_thu=4, hours_fri=4, hours_sat=0, hours_sun=0)
    punches = [_p_on(date(2026, 8, 3), "in", 8), _p_on(date(2026, 8, 3), "out", 16)]
    before = summarize_day(punches, date(2026, 8, 3), full, now=datetime(2026, 8, 3, 20, tzinfo=ZoneInfo("UTC")))
    after = summarize_day(punches, date(2026, 8, 3), part, now=datetime(2026, 8, 3, 20, tzinfo=ZoneInfo("UTC")))
    assert before["soll_hours"] == 8
    assert after["soll_hours"] == 4
    assert after["delta_hours"] - before["delta_hours"] == 4


def test_employment_window():
    from app.balance import hired_on, is_employed

    user = SimpleNamespace(
        hired_on=date(2026, 3, 1),
        left_on=date(2026, 8, 15),
        created_at=datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
    )
    assert hired_on(user) == date(2026, 3, 1)
    assert is_employed(user, date(2026, 3, 1))
    assert not is_employed(user, date(2026, 2, 28))
    assert is_employed(user, date(2026, 8, 15))
    assert not is_employed(user, date(2026, 8, 16))


def test_employment_falls_back_to_created_at():
    from app.balance import hired_on, is_employed

    user = SimpleNamespace(hired_on=None, left_on=None, created_at=datetime(2026, 9, 1, 10, tzinfo=ZoneInfo("UTC")))
    assert hired_on(user) == date(2026, 9, 1)
    assert not is_employed(user, date(2026, 8, 31))
    assert is_employed(user, date(2026, 9, 1))


def test_outside_employment_zeroes_account():
    from app.balance import summarize_user_day

    model = SimpleNamespace(
        hours_mon=8,
        hours_tue=8,
        hours_wed=8,
        hours_thu=8,
        hours_fri=8,
        hours_sat=0,
        hours_sun=0,
    )
    user = SimpleNamespace(
        hired_on=date(2026, 9, 4),
        left_on=None,
        created_at=None,
        work_model=model,
        auto_break=False,
    )
    punches = [_p_on(date(2026, 8, 3), "in", 8), _p_on(date(2026, 8, 3), "out", 16)]
    day = summarize_user_day(user, punches, date(2026, 8, 3), [], None, None)
    assert day["soll_hours"] == 0
    assert day["delta_hours"] == 0
    assert "missing_day" not in day["warnings"]
