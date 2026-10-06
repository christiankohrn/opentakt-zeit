from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.models import Punch
from app.timecalc import model_on_day, status_from_punches, summarize_day, work_intervals


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


def _full_week():
    return SimpleNamespace(
        hours_mon=8,
        hours_tue=8,
        hours_wed=8,
        hours_thu=8,
        hours_fri=8,
        hours_sat=0,
        hours_sun=0,
        break_after_minutes=0,
        break_minutes=0,
        flex_enabled=True,
    )


def test_vacation_and_sick_fill_the_target():
    model = _full_week()
    now = datetime(2026, 8, 6, tzinfo=ZoneInfo("UTC"))
    vacation = summarize_day(
        [],
        date(2026, 8, 5),
        model,
        now=now,
        absence=SimpleNamespace(kind="vacation", note="Urlaub"),
    )
    assert vacation["work_hours"] == 8
    assert vacation["delta_hours"] == 0
    assert vacation["absence"]["kind"] == "vacation"
    assert vacation["warnings"] == []
    sick = summarize_day([], date(2026, 8, 5), model, now=now, absence=SimpleNamespace(kind="sick", note=""))
    assert sick["work_hours"] == 8
    assert sick["delta_hours"] == 0


def test_school_fills_and_comp_time_keeps_the_deficit():
    model = _full_week()
    now = datetime(2026, 8, 6, tzinfo=ZoneInfo("UTC"))
    school = summarize_day(
        [],
        date(2026, 8, 5),
        model,
        now=now,
        absence=SimpleNamespace(kind="school", note=None),
    )
    assert school["work_hours"] == 8
    assert school["delta_hours"] == 0
    assert school["warnings"] == []
    leave = summarize_day(
        [],
        date(2026, 8, 5),
        model,
        now=now,
        absence=SimpleNamespace(kind="special_leave", note=None),
    )
    assert leave["work_hours"] == 8 and leave["delta_hours"] == 0
    comp = summarize_day(
        [],
        date(2026, 8, 5),
        model,
        now=now,
        absence=SimpleNamespace(kind="comp_time", note=None),
    )
    assert comp["work_hours"] == 0
    assert comp["delta_hours"] == -8
    assert "missing_day" not in comp["warnings"]


def test_stamps_on_vacation_count_as_plus():
    punches = [_p_on(date(2026, 8, 5), "in", 7), _p_on(date(2026, 8, 5), "out", 9)]
    day = summarize_day(
        punches,
        date(2026, 8, 5),
        _full_week(),
        now=datetime(2026, 8, 6, tzinfo=ZoneInfo("UTC")),
        absence=SimpleNamespace(kind="vacation", note=""),
    )
    assert abs(day["work_hours"] - 10) < 0.05
    assert abs(day["delta_hours"] - 2) < 0.05
    assert day["first_in"] == "07:00"


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


def test_open_shift_does_not_paint_the_next_day_before_it_starts():
    punches = [_p_on(date(2026, 9, 29), "in", 7, 24)]
    now = datetime(2026, 9, 29, 7, 43, tzinfo=ZoneInfo("UTC"))
    today = summarize_day(punches, date(2026, 9, 29), None, now=now)
    tomorrow = summarize_day(punches, date(2026, 9, 30), None, now=now)
    assert today["first_in"] == "07:24"
    assert today["open"] is True
    assert today["work_hours"] > 0
    assert tomorrow["first_in"] is None
    assert tomorrow["open"] is False
    assert tomorrow["work_hours"] == 0


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


def test_forgotten_checkout_accrues_no_phantom_time():
    punches = [
        _p_on(date(2026, 8, 24), "in", 14, 0),
        _p_on(date(2026, 8, 25), "in", 6, 0),
        _p_on(date(2026, 8, 25), "out", 14, 0),
    ]
    now = datetime(2026, 8, 26, tzinfo=ZoneInfo("UTC"))
    forgotten = summarize_day(punches, date(2026, 8, 24), _full_week(), now=now)
    assert "checkout_missing" in forgotten["warnings"]
    assert forgotten["work_hours"] == 0
    assert forgotten["open"] is True
    assert work_intervals(punches, date(2026, 8, 24), now=now) == []


def test_forgotten_checkout_without_any_later_punch():
    punches = [_p_on(date(2026, 8, 24), "in", 14, 0)]
    now = datetime(2026, 8, 26, tzinfo=ZoneInfo("UTC"))
    forgotten = summarize_day(punches, date(2026, 8, 24), _full_week(), now=now)
    assert "checkout_missing" in forgotten["warnings"]
    assert forgotten["work_hours"] == 0


def test_overnight_shift_still_accrues_until_midnight():
    punches = [
        _p_on(date(2026, 8, 7), "in", 22, 0),
        _p_on(date(2026, 8, 8), "out", 6, 0),
    ]
    now = datetime(2026, 8, 9, tzinfo=ZoneInfo("UTC"))
    night = summarize_day(punches, date(2026, 8, 7), None, now=now)
    assert "overnight" in night["warnings"]
    assert abs(night["work_hours"] - 2.0) < 0.05
    assert len(work_intervals(punches, date(2026, 8, 7), now=now)) == 1


def test_second_clock_in_keeps_earliest_start():
    punches = [
        _p_on(date(2026, 8, 5), "in", 8, 0),
        _p_on(date(2026, 8, 5), "in", 8, 5),
        _p_on(date(2026, 8, 5), "out", 17, 0),
    ]
    day = summarize_day(punches, date(2026, 8, 5), None, now=datetime(2026, 8, 6, tzinfo=ZoneInfo("UTC")))
    assert day["first_in"] == "08:00"
    assert abs(day["work_hours"] - 9.0) < 0.05
    spans = work_intervals(punches, date(2026, 8, 5), now=datetime(2026, 8, 6, tzinfo=ZoneInfo("UTC")))
    assert len(spans) == 1
    assert (spans[0][1] - spans[0][0]).total_seconds() == 9 * 3600


def test_stray_clock_in_during_break_counts_nothing_twice():
    punches = [
        _p_on(date(2026, 8, 5), "in", 8, 0),
        _p_on(date(2026, 8, 5), "break_start", 12, 0),
        _p_on(date(2026, 8, 5), "in", 12, 30),
        _p_on(date(2026, 8, 5), "break_end", 13, 0),
        _p_on(date(2026, 8, 5), "out", 17, 0),
    ]
    day = summarize_day(punches, date(2026, 8, 5), None, now=datetime(2026, 8, 6, tzinfo=ZoneInfo("UTC")))
    assert abs(day["work_hours"] - 8.0) < 0.05
    assert abs(day["break_hours"] - 1.0) < 0.05


def test_future_workday_has_no_delta():
    now = datetime(2026, 8, 18, tzinfo=ZoneInfo("UTC"))
    future = summarize_day([], date(2026, 8, 19), _full_week(), now=now)
    assert future["soll_hours"] == 8
    assert future["work_hours"] == 0
    assert future["delta_hours"] == 0
    assert future["warnings"] == []


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


def test_seconds_are_dropped_before_the_duration():
    day = date(2026, 9, 9)

    def at(kind: str, hour: int, minute: int, second: int) -> Punch:
        t = datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(
            ZoneInfo("UTC")
        )
        return Punch(user_id=1, kind=kind, server_time=t, source="test")

    punches = [at("in", 7, 50, 40), at("out", 16, 18, 50)]
    result = summarize_day(
        punches,
        day,
        _full_week(),
        now=datetime(2026, 9, 10, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["first_in"] == "07:50"
    assert result["last_out"] == "16:18"
    assert result["auto_break_minutes"] == 30
    assert abs(result["work_hours"] - (8 + 28 / 60 - 0.5)) < 1e-9
    from app.balance import format_hm

    assert format_hm(result["work_hours"]) == "7:58"
    assert format_hm(result["delta_hours"], signed=True) == "-0:02"


def test_auto_break_follows_the_six_and_nine_hour_steps():
    from app.balance import format_hm

    def span(day: date, start: tuple[int, int], end: tuple[int, int]) -> dict:
        punches = [_p_on(day, "in", *start), _p_on(day, "out", *end)]
        return summarize_day(
            punches,
            day,
            _full_week(),
            now=datetime(day.year, day.month, day.day, 22, tzinfo=ZoneInfo("Europe/Berlin")),
            auto_break=True,
        )

    partial = span(date(2026, 9, 17), (8, 0), (14, 13))
    assert partial["auto_break_minutes"] == 13
    assert format_hm(partial["work_hours"]) == "6:00"
    assert format_hm(partial["delta_hours"], signed=True) == "-2:00"

    split = summarize_day(
        [
            _p_on(date(2026, 9, 17), "in", 7, 43),
            _p_on(date(2026, 9, 17), "out", 11, 12),
            _p_on(date(2026, 9, 17), "in", 14, 0),
            _p_on(date(2026, 9, 17), "out", 16, 44),
        ],
        date(2026, 9, 17),
        _full_week(),
        now=datetime(2026, 9, 18, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert split["auto_break_minutes"] == 13
    assert format_hm(split["work_hours"]) == "6:00"

    nine = span(date(2026, 9, 7), (7, 20), (16, 38))
    assert nine["auto_break_minutes"] == 30
    assert format_hm(nine["work_hours"]) == "8:48"

    capped = span(date(2026, 8, 3), (7, 12), (16, 43))
    assert capped["auto_break_minutes"] == 31
    assert format_hm(capped["work_hours"]) == "9:00"
    assert format_hm(capped["delta_hours"], signed=True) == "+1:00"

    full = span(date(2026, 8, 4), (7, 0), (16, 46))
    assert full["auto_break_minutes"] == 45
    assert format_hm(full["work_hours"]) == "9:01"


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
