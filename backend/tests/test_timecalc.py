import json
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.models import Punch
from app.timecalc import model_on_day, status_from_punches, summarize_day, work_intervals


def _p(kind: str, hour: int, minute: int = 0) -> Punch:
    t = datetime(2026, 9, 4, hour, minute, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(ZoneInfo("UTC"))
    return Punch(user_id=1, kind=kind, server_time=t, source="test")


def _p_on(day: date, kind: str, hour: int, minute: int = 0, second: int = 0) -> Punch:
    t = datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(
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


def test_sick_only_fills_the_gap_beside_attendance():
    day = date(2026, 8, 4)
    now = datetime(2026, 8, 5, tzinfo=ZoneInfo("UTC"))
    model = _full_week()
    model.hours_tue = 7.6
    sick = SimpleNamespace(kind="sick", note="")
    partial = summarize_day(
        [_p_on(day, "in", 7, 44), _p_on(day, "out", 8, 15)],
        day,
        model,
        now=now,
        absence=sick,
        auto_break=False,
    )
    assert abs(partial["work_hours"] - 7.6) < 0.02
    assert abs(partial["delta_hours"]) < 0.02

    longer = summarize_day(
        [_p_on(day, "in", 7), _p_on(day, "out", 16)],
        day,
        model,
        now=now,
        absence=sick,
        auto_break=False,
    )
    assert abs(longer["work_hours"] - 9) < 0.02
    assert abs(longer["delta_hours"] - 1.4) < 0.02


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


def test_pause_after_checkout_does_not_reopen_the_next_day():
    """24.09. endet mit Pause ohne weiteres Gehen. Der 25.09. beginnt nicht um Mitternacht."""
    from app.balance import format_hm

    punches = [
        _p_on(date(2026, 9, 24), "in", 6, 3),
        _p_on(date(2026, 9, 24), "out", 8, 10),
        _p_on(date(2026, 9, 24), "in", 8, 16),
        _p_on(date(2026, 9, 24), "out", 9, 46),
        _p_on(date(2026, 9, 24), "in", 9, 51),
        _p_on(date(2026, 9, 24), "out", 11, 37),
        _p_on(date(2026, 9, 24), "break_start", 11, 37),
        _p_on(date(2026, 9, 24), "break_end", 12, 9),
        _p_on(date(2026, 9, 25), "in", 6, 24),
        _p_on(date(2026, 9, 25), "out", 8, 53),
        _p_on(date(2026, 9, 25), "in", 8, 58),
        _p_on(date(2026, 9, 25), "out", 12, 2),
        _p_on(date(2026, 9, 25), "break_start", 12, 2),
        _p_on(date(2026, 9, 25), "break_end", 12, 35),
        _p_on(date(2026, 9, 25), "in", 12, 35),
        _p_on(date(2026, 9, 25), "out", 14, 32),
    ]
    now = datetime(2026, 9, 26, tzinfo=ZoneInfo("UTC"))
    model = _rounded_model()
    thursday = summarize_day(punches, date(2026, 9, 24), model, now=now, auto_break=True)
    friday = summarize_day(punches, date(2026, 9, 25), model, now=now, auto_break=True)
    assert status_from_punches(punches[:8]) == "away"
    assert thursday["first_in"] == "06:15"
    assert format_hm(thursday["work_hours"]) == "5:11"
    assert format_hm(thursday["delta_hours"], signed=True) == "-2:25"
    assert friday["first_in"] == "06:30"
    assert friday["last_out"] == "14:32"
    assert format_hm(friday["work_hours"]) == "7:24"
    assert format_hm(friday["delta_hours"], signed=True) == "-0:12"
    assert "over_10h" not in friday["warnings"]


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


def test_auto_break_tops_up_a_short_stamped_pause():
    from app.balance import format_hm

    now = datetime(2026, 9, 5, tzinfo=ZoneInfo("UTC"))
    short_four = summarize_day(
        [_p("in", 8), _p("break_start", 12), _p("break_end", 12, 26), _p("out", 16, 26)],
        date(2026, 9, 4),
        _full_week(),
        now=now,
        auto_break=True,
    )
    assert short_four["auto_break_minutes"] == 4
    assert abs(short_four["break_hours"] - 0.5) < 1e-9
    assert format_hm(short_four["delta_hours"], signed=True) == "-0:04"
    assert "break_short" not in short_four["warnings"]

    short_ten = summarize_day(
        [_p("in", 8), _p("break_start", 12), _p("break_end", 12, 20), _p("out", 16, 40)],
        date(2026, 9, 4),
        _full_week(),
        now=now,
        auto_break=True,
    )
    assert short_ten["auto_break_minutes"] == 10
    assert abs(short_ten["break_hours"] - 0.5) < 1e-9
    assert format_hm(short_ten["work_hours"]) == "8:10"
    assert format_hm(short_ten["delta_hours"], signed=True) == "+0:10"
    assert "break_short" not in short_ten["warnings"]

    longer = summarize_day(
        [_p("in", 8), _p("break_start", 12), _p("break_end", 12, 40), _p("out", 16, 30)],
        date(2026, 9, 4),
        _full_week(),
        now=now,
        auto_break=True,
    )
    assert longer["auto_break_minutes"] == 0
    assert format_hm(longer["break_hours"]) == "0:40"
    assert format_hm(longer["work_hours"]) == "7:50"


def test_pause_between_checkout_and_checkin_is_not_deducted_twice():
    from app.balance import format_hm

    day = date(2026, 8, 3)
    model = SimpleNamespace(
        hours_mon=7.6,
        hours_tue=7.6,
        hours_wed=7.6,
        hours_thu=7.6,
        hours_fri=7.6,
        hours_sat=0,
        hours_sun=0,
    )
    punches = [
        _p_on(day, "in", 6, 30),
        _p_on(day, "out", 10, 40),
        _p_on(day, "break_start", 10, 40),
        _p_on(day, "break_end", 11, 10),
        _p_on(day, "in", 11, 10),
        _p_on(day, "out", 14, 33),
    ]
    result = summarize_day(
        punches,
        day,
        model,
        now=datetime(2026, 8, 4, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["auto_break_minutes"] == 0
    assert format_hm(result["break_hours"]) == "0:30"
    assert format_hm(result["work_hours"]) == "7:33"
    assert format_hm(result["delta_hours"], signed=True) == "-0:03"
    assert "break_short" not in result["warnings"]


def _rounded_model(**extra):
    base = dict(
        hours_mon=7.6,
        hours_tue=7.6,
        hours_wed=7.6,
        hours_thu=7.6,
        hours_fri=7.6,
        hours_sat=0,
        hours_sun=0,
        round_start_before=0,
        round_start_after=0,
        round_end_before=0,
        round_end_after=0,
        round_first_threshold=2,
        round_first_step=15,
        round_last_threshold=0,
        round_last_step=0,
        booking_corridor="",
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_first_booking_rounds_up_from_two_minutes():
    from app.balance import format_hm

    day = date(2026, 8, 7)
    punches = [
        _p_on(day, "in", 6, 24),
        _p_on(day, "out", 10, 39),
        _p_on(day, "break_start", 10, 39),
        _p_on(day, "break_end", 11, 7),
        _p_on(day, "in", 11, 7),
        _p_on(day, "out", 14, 46),
    ]
    result = summarize_day(
        punches,
        day,
        _rounded_model(),
        now=datetime(2026, 8, 8, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["first_in"] == "06:30"
    assert result["last_out"] == "14:46"
    assert result["punches"][0]["time"] == "06:24"
    assert format_hm(result["work_hours"]) == "7:46"
    assert format_hm(result["delta_hours"], signed=True) == "+0:10"

    early = summarize_day(
        [_p_on(day, "in", 6, 1), _p_on(day, "out", 14, 0)],
        day,
        _rounded_model(),
        now=datetime(2026, 8, 8, tzinfo=ZoneInfo("UTC")),
        auto_break=False,
    )
    assert early["first_in"] == "06:00"


def test_comp_time_does_not_round_the_first_booking():
    from app.balance import format_hm

    model = _rounded_model()
    now = datetime(2026, 8, 27, tzinfo=ZoneInfo("UTC"))
    comp = SimpleNamespace(kind="comp_time", note=None)

    def day_with(day: date, punches: list[Punch], absence=comp) -> dict:
        return summarize_day(punches, day, model, now=now, auto_break=True, absence=absence)

    monday = date(2026, 8, 24)
    arrived = day_with(
        monday,
        [
            _p_on(monday, "in", 7, 28),
            _p_on(monday, "out", 12, 30),
            _p_on(monday, "break_start", 12, 30),
            _p_on(monday, "break_end", 13, 0),
            _p_on(monday, "in", 13, 0),
            _p_on(monday, "out", 15, 45),
        ],
    )
    assert arrived["first_in"] == "07:28"
    assert format_hm(arrived["work_hours"]) == "7:47"
    assert format_hm(arrived["delta_hours"], signed=True) == "+0:11"
    plain = day_with(
        monday,
        [
            _p_on(monday, "in", 7, 28),
            _p_on(monday, "out", 12, 30),
            _p_on(monday, "break_start", 12, 30),
            _p_on(monday, "break_end", 13, 0),
            _p_on(monday, "in", 13, 0),
            _p_on(monday, "out", 15, 45),
        ],
        absence=None,
    )
    assert plain["first_in"] == "07:30"
    assert format_hm(plain["work_hours"]) == "7:45"

    tuesday = date(2026, 8, 25)
    partial = day_with(
        tuesday,
        [
            _p_on(tuesday, "in", 7, 14),
            _p_on(tuesday, "out", 12, 47),
            _p_on(tuesday, "break_start", 12, 47),
            _p_on(tuesday, "break_end", 13, 16),
            _p_on(tuesday, "in", 13, 16),
            _p_on(tuesday, "out", 15, 45),
        ],
    )
    assert partial["first_in"] == "07:14"
    assert format_hm(partial["work_hours"]) == "8:01"
    assert format_hm(partial["delta_hours"], signed=True) == "+0:25"

    wednesday = date(2026, 8, 26)
    wider = day_with(
        wednesday,
        [
            _p_on(wednesday, "in", 7, 11),
            _p_on(wednesday, "out", 12, 39),
            _p_on(wednesday, "break_start", 12, 39),
            _p_on(wednesday, "break_end", 13, 5),
            _p_on(wednesday, "in", 13, 5),
            _p_on(wednesday, "out", 15, 45),
        ],
    )
    assert wider["first_in"] == "07:11"
    assert format_hm(wider["work_hours"]) == "8:04"
    assert format_hm(wider["delta_hours"], signed=True) == "+0:28"


def test_rounding_threshold_includes_the_whole_minute():
    from app.balance import format_hm

    day = date(2026, 8, 3)
    now = datetime(2026, 8, 4, tzinfo=ZoneInfo("UTC"))
    model = _rounded_model()
    within = summarize_day(
        [_p_on(day, "in", 6, 2, 40), _p_on(day, "out", 14, 46)],
        day,
        model,
        now=now,
        auto_break=False,
    )
    assert within["first_in"] == "06:00"
    crossed = summarize_day(
        [_p_on(day, "in", 6, 3), _p_on(day, "out", 14, 46)],
        day,
        model,
        now=now,
        auto_break=False,
    )
    assert crossed["first_in"] == "06:15"

    result = summarize_day(
        [
            _p_on(day, "in", 6, 2),
            _p_on(day, "out", 8, 7),
            _p_on(day, "in", 8, 16),
            _p_on(day, "out", 10, 50),
            _p_on(day, "break_start", 10, 50),
            _p_on(day, "break_end", 11, 16),
            _p_on(day, "in", 11, 16),
            _p_on(day, "out", 14, 46),
        ],
        day,
        model,
        now=now,
        auto_break=True,
    )
    assert result["first_in"] == "06:00"
    assert result["last_out"] == "14:46"
    assert result["punches"][0]["time"] == "06:02"
    assert format_hm(result["work_hours"]) == "8:07"
    assert format_hm(result["delta_hours"], signed=True) == "+0:31"


def test_corridor_drops_time_before_the_start_and_can_pull_the_end():
    day = date(2026, 8, 7)
    corridor = json.dumps({"fri": {"start": "06:30", "end": "14:00"}})
    snapped = summarize_day(
        [_p_on(day, "in", 6, 20), _p_on(day, "out", 14, 46)],
        day,
        _rounded_model(round_first_step=0, round_first_threshold=0, round_start_before=15, booking_corridor=corridor),
        now=datetime(2026, 8, 8, tzinfo=ZoneInfo("UTC")),
        auto_break=False,
    )
    assert snapped["first_in"] == "06:30"
    assert snapped["last_out"] == "14:00"

    clipped = summarize_day(
        [_p_on(day, "in", 5, 30), _p_on(day, "out", 14, 10)],
        day,
        _rounded_model(
            round_first_step=0,
            round_first_threshold=0,
            round_end_after=20,
            booking_corridor=corridor,
        ),
        now=datetime(2026, 8, 8, tzinfo=ZoneInfo("UTC")),
        auto_break=False,
    )
    assert clipped["first_in"] == "06:30"
    assert clipped["last_out"] == "14:00"


def test_corridor_drops_time_after_the_end():
    from app.balance import format_hm

    day = date(2026, 8, 27)
    corridor = json.dumps({"thu": {"start": "05:00", "end": "16:00"}})
    result = summarize_day(
        [
            _p_on(day, "in", 7, 14),
            _p_on(day, "out", 12, 35),
            _p_on(day, "break_start", 12, 35),
            _p_on(day, "break_end", 13, 6),
            _p_on(day, "in", 13, 6),
            _p_on(day, "out", 16, 40),
        ],
        day,
        _rounded_model(booking_corridor=corridor),
        now=datetime(2026, 8, 28, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["first_in"] == "07:15"
    assert result["last_out"] == "16:00"
    assert result["punches"][-1]["time"] == "16:40"
    assert format_hm(result["work_hours"]) == "8:14"
    assert format_hm(result["delta_hours"], signed=True) == "+0:38"


def _three_shifts() -> str:
    return json.dumps(
        [
            {"name": "Früh", "start": "05:45", "end": "14:00"},
            {"name": "Spät", "start": "13:30", "end": "22:00"},
            {"name": "Nacht", "start": "21:00", "end": "06:00"},
        ]
    )


def test_later_bookings_stay_on_the_first_shift():
    shifts = json.dumps(
        [
            {"name": "Früh", "days": {"mon": {"start": "06:00", "end": "14:00"}}},
            {"name": "Spät", "days": {"mon": {"start": "13:45", "end": "22:00"}}},
        ]
    )
    day = date(2026, 8, 3)
    model = _rounded_model(shifts=shifts, round_first_step=0, round_first_threshold=0, hours_mon=8)
    result = summarize_day(
        [
            _p_on(day, "in", 6, 35),
            _p_on(day, "out", 10, 34),
            _p_on(day, "in", 10, 40),
            _p_on(day, "out", 13, 0),
            _p_on(day, "in", 13, 4),
            _p_on(day, "out", 14, 10),
        ],
        day,
        model,
        now=datetime(2026, 8, 4, tzinfo=ZoneInfo("UTC")),
        auto_break=False,
    )
    assert result["shift"] == "Früh"
    assert result["first_in"] == "06:35"
    assert result["last_out"] == "14:00"
    assert abs(result["work_hours"] - (7 + 15 / 60)) < 0.02


def test_shift_follows_the_nearest_start_and_its_corridor():
    day = date(2026, 8, 27)
    now = datetime(2026, 8, 28, tzinfo=ZoneInfo("UTC"))
    model = _rounded_model(shifts=_three_shifts(), round_first_step=0, round_first_threshold=0)
    early = summarize_day(
        [_p_on(day, "in", 6, 24), _p_on(day, "out", 14, 46)],
        day,
        model,
        now=now,
        auto_break=False,
    )
    assert early["shift"] == "Früh"
    assert early["first_in"] == "06:24"
    assert early["last_out"] == "14:00"

    late = summarize_day(
        [_p_on(day, "in", 14, 10), _p_on(day, "out", 22, 20)],
        day,
        model,
        now=now,
        auto_break=False,
    )
    assert late["shift"] == "Spät"
    assert late["first_in"] == "14:10"
    assert late["last_out"] == "22:00"

    before = summarize_day(
        [_p_on(day, "in", 5, 30), _p_on(day, "out", 13, 0)],
        day,
        model,
        now=now,
        auto_break=False,
    )
    assert before["shift"] == "Früh"
    assert before["first_in"] == "05:45"


def test_night_shift_end_clips_the_next_morning():
    punches = [
        _p_on(date(2026, 8, 7), "in", 22, 0),
        _p_on(date(2026, 8, 8), "out", 6, 10),
    ]
    now = datetime(2026, 8, 9, tzinfo=ZoneInfo("UTC"))
    model = _rounded_model(shifts=_three_shifts(), round_first_step=0, round_first_threshold=0)
    night = summarize_day(punches, date(2026, 8, 7), model, now=now)
    morning = summarize_day(punches, date(2026, 8, 8), model, now=now)
    assert night["shift"] == "Nacht"
    assert night["first_in"] == "22:00"
    assert night["last_out"] == "06:00"
    assert abs(night["work_hours"] - 8.0) < 0.02
    assert "overnight" not in night["warnings"]
    assert morning["shift"] is None
    assert morning["work_hours"] == 0
    assert morning["span_punches"] == []


def test_night_shift_uses_the_start_day_and_only_its_weekday_corridor():
    shifts = json.dumps(
        [
            {
                "name": "Nacht",
                "days": {key: {"start": "21:45", "end": "06:00"} for key in ("mon", "tue", "wed", "thu", "fri")},
            }
        ]
    )
    model = _rounded_model(shifts=shifts, round_first_step=15, round_first_threshold=2)
    sunday = date(2026, 8, 9)
    monday = date(2026, 8, 10)
    thursday = date(2026, 8, 13)
    friday = date(2026, 8, 14)
    punches = [
        _p_on(sunday, "in", 21, 39),
        _p_on(monday, "out", 6, 9),
        _p_on(monday, "in", 21, 46),
        _p_on(date(2026, 8, 11), "out", 6, 9),
        _p_on(thursday, "in", 21, 37),
        _p_on(friday, "out", 6, 13),
    ]
    now = datetime(2026, 8, 15, tzinfo=ZoneInfo("UTC"))
    sun = summarize_day(punches, sunday, model, now=now, auto_break=True)
    mon = summarize_day(punches, monday, model, now=now, auto_break=True)
    thu = summarize_day(punches, thursday, model, now=now, auto_break=True)
    fri = summarize_day(punches, friday, model, now=now, auto_break=True)
    assert sun["shift"] is None
    assert sun["first_in"] == "21:39"
    assert sun["last_out"] == "06:09"
    assert abs(sun["work_hours"] - 8.0) < 0.02
    assert [p["time"] for p in sun["span_punches"]] == ["21:39", "06:09"]
    assert mon["shift"] == "Nacht"
    assert mon["first_in"] == "21:45"
    assert mon["last_out"] == "06:00"
    assert abs(mon["work_hours"] - 7.75) < 0.02
    assert abs(mon["delta_hours"] - 0.15) < 0.02
    assert [p["kind"] for p in mon["span_punches"]] == ["in", "out"]
    assert thu["first_in"] == "21:45"
    assert thu["last_out"] == "06:00"
    assert abs(thu["work_hours"] - 7.75) < 0.02
    assert fri["work_hours"] == 0
    assert fri["span_punches"] == []
    assert "missing_day" in fri["warnings"]
    assert fri["punches"][0]["time"] == "06:13"


def test_shift_day_without_a_corridor_keeps_every_booking():
    shifts = json.dumps([{"name": "Früh", "days": {"mon": {"start": "05:45", "end": "14:00"}}}])
    model = _rounded_model(shifts=shifts, round_first_step=0, round_first_threshold=0)
    monday = date(2026, 8, 3)
    thursday = date(2026, 8, 27)
    clipped = summarize_day(
        [_p_on(monday, "in", 6, 24), _p_on(monday, "out", 14, 46)],
        monday,
        model,
        now=datetime(2026, 8, 4, tzinfo=ZoneInfo("UTC")),
        auto_break=False,
    )
    open_day = summarize_day(
        [_p_on(thursday, "in", 6, 24), _p_on(thursday, "out", 14, 46)],
        thursday,
        model,
        now=datetime(2026, 8, 28, tzinfo=ZoneInfo("UTC")),
        auto_break=False,
    )
    assert clipped["shift"] == "Früh"
    assert clipped["first_in"] == "06:24"
    assert clipped["last_out"] == "14:00"
    assert open_day["shift"] is None
    assert open_day["first_in"] == "06:24"
    assert open_day["last_out"] == "14:46"


def test_day_model_replaces_soll_and_corridor_for_that_day_only():
    from app.balance import summarize_user_day

    usual = _rounded_model(
        id=1,
        name="Vollzeit",
        booking_corridor=json.dumps({"thu": {"start": "05:00", "end": "16:00"}, "fri": {"start": "05:00", "end": "16:00"}}),
        round_first_step=0,
        round_first_threshold=0,
    )
    late = _rounded_model(
        id=2,
        name="Spät",
        hours_thu=6.0,
        booking_corridor=json.dumps({"thu": {"start": "13:00", "end": "22:00"}}),
        round_first_step=0,
        round_first_threshold=0,
    )
    user = SimpleNamespace(hired_on=date(2020, 1, 1), left_on=None, created_at=None, work_model=usual, auto_break=False)
    timeline = [(date(2000, 1, 1), usual)]
    thursday = date(2026, 8, 27)
    friday = date(2026, 8, 28)
    punches = [
        _p_on(thursday, "in", 12, 0),
        _p_on(thursday, "out", 21, 0),
        _p_on(friday, "in", 12, 0),
        _p_on(friday, "out", 21, 0),
    ]
    once = summarize_user_day(user, punches, thursday, timeline, model_override=late)
    nxt = summarize_user_day(user, punches, friday, timeline)
    assert once["model_name"] == "Spät"
    assert once["day_model"] is True
    assert once["soll_hours"] == 6.0
    assert once["first_in"] == "13:00"
    assert once["last_out"] == "21:00"
    assert nxt["model_name"] == "Vollzeit"
    assert nxt["day_model"] is False
    assert nxt["soll_hours"] == 7.6
    assert nxt["first_in"] == "12:00"
    assert nxt["last_out"] == "16:00"


def test_auto_break_tops_up_only_the_overhang_above_six_hours():
    from app.balance import format_hm

    day = date(2026, 9, 17)
    topped = summarize_day(
        [
            _p_on(day, "in", 8, 0),
            _p_on(day, "break_start", 12, 0),
            _p_on(day, "break_end", 12, 5),
            _p_on(day, "out", 14, 13),
        ],
        day,
        _full_week(),
        now=datetime(2026, 9, 18, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert topped["auto_break_minutes"] == 8
    assert format_hm(topped["break_hours"]) == "0:13"
    assert format_hm(topped["work_hours"]) == "6:00"
    assert "break_short" not in topped["warnings"]


def test_break_window_sits_on_the_rounded_start():
    """16.09.: Beginn 06:15, Fenster 12:15–12:45, 21 Minuten Stempel, Rest 9."""
    from app.balance import format_hm

    day = date(2026, 9, 16)
    result = summarize_day(
        [
            _p_on(day, "in", 6, 10),
            _p_on(day, "out", 8, 29),
            _p_on(day, "in", 8, 36),
            _p_on(day, "out", 10, 39),
            _p_on(day, "break_start", 10, 39),
            _p_on(day, "break_end", 11, 0),
            _p_on(day, "in", 11, 0),
            _p_on(day, "out", 12, 45),
        ],
        day,
        _rounded_model(),
        now=datetime(2026, 9, 17, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["first_in"] == "06:15"
    assert result["auto_break_minutes"] == 9
    assert format_hm(result["break_hours"]) == "0:30"
    assert format_hm(result["work_hours"]) == "5:53"
    assert format_hm(result["delta_hours"], signed=True) == "-1:43"


def test_nine_hour_window_stays_closed_until_work_reaches_it():
    """31.08.: 8:55 Arbeit, Uhr schon bei Beginn plus 9 Stunden. Pause bleibt 30."""
    from app.balance import format_hm

    day = date(2026, 8, 31)
    result = summarize_day(
        [
            _p_on(day, "in", 6, 4),
            _p_on(day, "out", 8, 6),
            _p_on(day, "in", 8, 14),
            _p_on(day, "out", 10, 41),
            _p_on(day, "break_start", 10, 41),
            _p_on(day, "break_end", 11, 9),
            _p_on(day, "in", 11, 9),
            _p_on(day, "out", 15, 46),
        ],
        day,
        _rounded_model(),
        now=datetime(2026, 9, 1, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["first_in"] == "06:15"
    assert result["auto_break_minutes"] == 2
    assert format_hm(result["break_hours"]) == "0:30"
    assert format_hm(result["work_hours"]) == "8:53"
    assert format_hm(result["delta_hours"], signed=True) == "+1:17"


def test_break_window_in_a_gap_is_not_deducted():
    from app.balance import format_hm

    day = date(2026, 9, 17)
    missed = summarize_day(
        [
            _p_on(day, "in", 8, 0),
            _p_on(day, "out", 13, 50),
            _p_on(day, "in", 14, 40),
            _p_on(day, "out", 17, 0),
        ],
        day,
        _full_week(),
        now=datetime(2026, 9, 18, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert missed["auto_break_minutes"] == 0
    assert format_hm(missed["work_hours"]) == "8:10"

    partial = summarize_day(
        [
            _p_on(day, "in", 8, 0),
            _p_on(day, "out", 13, 50),
            _p_on(day, "in", 14, 10),
            _p_on(day, "out", 17, 0),
        ],
        day,
        _full_week(),
        now=datetime(2026, 9, 18, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert partial["auto_break_minutes"] == 30
    assert format_hm(partial["work_hours"]) == "8:10"


def test_pause_window_stays_full_when_work_continues_after_a_short_gap():
    """03.08.: Korridor bis 14:00, Fenster 10:35–11:05, fünf Minuten davon in der Lücke."""
    from app.balance import format_hm

    day = date(2026, 8, 3)
    shifts = json.dumps([{"name": "Früh", "days": {"mon": {"start": "06:00", "end": "14:00"}}}])
    model = _rounded_model(
        round_first_step=0,
        round_first_threshold=0,
        shifts=shifts,
        break_rules=json.dumps([{"after_hours": 4, "minutes": 30}]),
    )
    result = summarize_day(
        [
            _p_on(day, "in", 6, 35),
            _p_on(day, "out", 10, 34),
            _p_on(day, "in", 10, 40),
            _p_on(day, "out", 13, 0),
            _p_on(day, "in", 13, 4),
            _p_on(day, "out", 14, 10),
        ],
        day,
        model,
        now=datetime(2026, 8, 4, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["shift"] == "Früh"
    assert result["first_in"] == "06:35"
    assert result["last_out"] == "14:00"
    assert result["auto_break_minutes"] == 30
    assert format_hm(result["work_hours"]) == "6:45"
    assert format_hm(result["delta_hours"], signed=True) == "-0:51"
    assert "break_short:30:4" not in result["warnings"]


def test_pause_stops_at_the_threshold_when_only_minutes_follow_the_window():
    """15.08.: 4:28 Arbeit, Fenster voll, zwei Minuten danach. Ist bleibt 4:00."""
    from app.balance import format_hm

    day = date(2026, 8, 15)
    model = _rounded_model(
        round_first_step=0,
        round_first_threshold=0,
        break_rules=json.dumps([{"after_hours": 4, "minutes": 30}]),
    )
    result = summarize_day(
        [
            _p_on(day, "in", 7, 2),
            _p_on(day, "out", 10, 2),
            _p_on(day, "in", 10, 6),
            _p_on(day, "out", 11, 34),
        ],
        day,
        model,
        now=datetime(2026, 8, 16, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["first_in"] == "07:02"
    assert result["last_out"] == "11:34"
    assert result["auto_break_minutes"] == 28
    assert format_hm(result["work_hours"]) == "4:00"
    assert format_hm(result["delta_hours"], signed=True) == "+4:00"
    assert result["warnings"] == []


def test_stamped_pause_still_tops_up_when_work_is_only_just_over_six_hours():
    """31.08.: Beginn 07:13 wird 07:15, 27 Minuten Stempel, drei Minuten fehlen."""
    from app.balance import format_hm

    day = date(2026, 8, 31)
    result = summarize_day(
        [
            _p_on(day, "in", 7, 13),
            _p_on(day, "out", 11, 59),
            _p_on(day, "break_start", 11, 59),
            _p_on(day, "break_end", 12, 26),
            _p_on(day, "in", 12, 26),
            _p_on(day, "out", 13, 51),
        ],
        day,
        _rounded_model(),
        now=datetime(2026, 9, 1, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["first_in"] == "07:15"
    assert result["last_out"] == "13:51"
    assert result["auto_break_minutes"] == 3
    assert format_hm(result["break_hours"]) == "0:30"
    assert format_hm(result["work_hours"]) == "6:06"
    assert format_hm(result["delta_hours"], signed=True) == "-1:30"
    assert "break_short" not in result["warnings"]


def _break_model(rules: list[dict]):
    model = _full_week()
    model.break_rules = json.dumps(rules)
    return model


def test_break_threshold_keeps_the_minutes():
    from app.timecalc import break_steps

    model = SimpleNamespace(break_rules=json.dumps([{"after_hours": 9.75, "minutes": 45}]))
    assert break_steps(model) == [(9 * 60 + 45, 45)]


def test_fixed_pause_window_is_deducted_besides_a_later_stamp():
    """23.09.: feste Pause 12:00–12:30, zwei Minuten Stempel direkt danach."""
    from app.balance import format_hm

    day = date(2026, 9, 23)
    fixed = {key: {"start": "12:00", "end": "12:30"} for key in ("mon", "tue", "wed", "thu", "fri")}
    model = _rounded_model(break_mode="fixed", fixed_breaks=json.dumps(fixed))
    result = summarize_day(
        [
            _p_on(day, "in", 6, 47),
            _p_on(day, "out", 12, 30),
            _p_on(day, "break_start", 12, 30),
            _p_on(day, "in", 12, 32),
            _p_on(day, "break_end", 12, 32),
            _p_on(day, "out", 16, 17),
        ],
        day,
        model,
        now=datetime(2026, 9, 24, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["first_in"] == "06:45"
    assert result["last_out"] == "16:17"
    assert result["auto_break_minutes"] == 30
    assert format_hm(result["break_hours"]) == "0:32"
    assert format_hm(result["work_hours"]) == "9:00"
    assert format_hm(result["delta_hours"], signed=True) == "+1:24"
    assert result["warnings"] == []


def test_each_shift_uses_its_own_fixed_pause():
    from app.balance import format_hm

    day = date(2026, 9, 23)
    shifts = [
        {
            "name": "Früh",
            "days": {"wed": {"start": "06:00", "end": "17:00", "pause_start": "12:00", "pause_end": "12:30"}},
        },
        {
            "name": "Spät",
            "days": {"wed": {"start": "14:00", "end": "22:00", "pause_start": "18:00", "pause_end": "18:30"}},
        },
    ]
    model = SimpleNamespace(
        hours_mon=0,
        hours_tue=0,
        hours_wed=0,
        hours_thu=0,
        hours_fri=0,
        hours_sat=0,
        hours_sun=0,
        round_start_before=0,
        round_start_after=0,
        round_end_before=0,
        round_end_after=0,
        round_first_threshold=0,
        round_first_step=0,
        round_last_threshold=0,
        round_last_step=0,
        booking_corridor="",
        break_mode="fixed",
        fixed_breaks=json.dumps({"wed": {"start": "10:00", "end": "10:15"}}),
        shifts=json.dumps(shifts),
    )
    early = summarize_day(
        [
            _p_on(day, "in", 6, 45),
            _p_on(day, "out", 12, 30),
            _p_on(day, "in", 12, 32),
            _p_on(day, "out", 16, 17),
        ],
        day,
        model,
        now=datetime(2026, 9, 24, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert early["auto_break_minutes"] == 30
    assert format_hm(early["work_hours"]) == "9:00"
    late = summarize_day(
        [_p_on(day, "in", 14, 0), _p_on(day, "out", 22, 0)],
        day,
        model,
        now=datetime(2026, 9, 24, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert late["auto_break_minutes"] == 30
    assert format_hm(late["work_hours"]) == "7:30"


def _pause_only_model(days: dict):
    shifts = [
        {"name": "Früh", "days": days["Früh"]},
        {"name": "Spät", "days": days["Spät"]},
    ]
    return SimpleNamespace(
        hours_mon=7.6,
        hours_tue=7.6,
        hours_wed=7.6,
        hours_thu=7.6,
        hours_fri=7.6,
        hours_sat=0,
        hours_sun=0,
        round_start_before=0,
        round_start_after=0,
        round_end_before=0,
        round_end_after=0,
        round_first_threshold=0,
        round_first_step=0,
        round_last_threshold=0,
        round_last_step=0,
        booking_corridor="",
        break_mode="fixed",
        fixed_breaks="",
        shifts=json.dumps(shifts),
    )


def test_shift_pause_without_a_corridor_is_stored():
    from app.workmodels import normalize_shifts

    stored = normalize_shifts(
        [{"name": "Früh", "days": {"mon": {"pause_start": "12:00", "pause_end": "12:30"}}}]
    )
    assert stored[0]["days"]["mon"] == {"pause_start": "12:00", "pause_end": "12:30"}


def test_pause_inside_the_day_picks_the_shift_when_no_start_is_set():
    """21.09.: kein Korridor, Pause 12:00–12:30 liegt in 06:49–15:01, 19:30 nicht."""
    from app.balance import format_hm

    day = date(2026, 9, 21)
    model = _pause_only_model(
        {
            "Früh": {"mon": {"pause_start": "12:00", "pause_end": "12:30"}},
            "Spät": {"mon": {"pause_start": "19:30", "pause_end": "20:00"}},
        }
    )
    result = summarize_day(
        [_p_on(day, "in", 6, 49), _p_on(day, "out", 15, 1)],
        day,
        model,
        now=datetime(2026, 9, 22, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["shift"] == "Früh"
    assert result["last_out"] == "15:01"
    assert result["auto_break_minutes"] == 30
    assert format_hm(result["work_hours"]) == "7:42"
    assert "over_10h" not in result["warnings"]


def test_a_later_pause_wins_when_only_that_one_lies_in_the_day():
    from app.balance import format_hm

    day = date(2026, 9, 21)
    model = _pause_only_model(
        {
            "Früh": {"mon": {"pause_start": "12:00", "pause_end": "12:30"}},
            "Spät": {"mon": {"pause_start": "19:30", "pause_end": "20:00"}},
        }
    )
    result = summarize_day(
        [_p_on(day, "in", 16, 0), _p_on(day, "out", 22, 0)],
        day,
        model,
        now=datetime(2026, 9, 22, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["shift"] == "Spät"
    assert result["last_out"] == "22:00"
    assert result["auto_break_minutes"] == 30
    assert format_hm(result["work_hours"]) == "5:30"


def test_two_pauses_inside_one_day_count_only_the_closer_shift():
    from app.balance import format_hm

    day = date(2026, 9, 21)
    model = _pause_only_model(
        {
            "Früh": {"mon": {"pause_start": "12:00", "pause_end": "12:30"}},
            "Spät": {"mon": {"pause_start": "19:30", "pause_end": "20:00"}},
        }
    )
    result = summarize_day(
        [_p_on(day, "in", 6, 0), _p_on(day, "out", 22, 0)],
        day,
        model,
        now=datetime(2026, 9, 22, tzinfo=ZoneInfo("UTC")),
        auto_break=True,
    )
    assert result["shift"] == "Früh"
    assert result["auto_break_minutes"] == 30
    assert format_hm(result["work_hours"]) == "15:30"


def test_break_rules_on_the_model_can_start_at_four_hours():
    from app.balance import format_hm

    model = _break_model([{"after_hours": 4, "minutes": 30}, {"after_hours": 9, "minutes": 45}])
    now = datetime(2026, 9, 18, tzinfo=ZoneInfo("UTC"))
    day = date(2026, 9, 17)

    def span(start: tuple[int, int], end: tuple[int, int], auto: bool = True) -> dict:
        return summarize_day(
            [_p_on(day, "in", *start), _p_on(day, "out", *end)],
            day,
            model,
            now=now,
            auto_break=auto,
        )

    short = span((8, 0), (11, 30))
    assert short["auto_break_minutes"] == 0
    assert format_hm(short["work_hours"]) == "3:30"

    ramp = span((8, 0), (12, 10))
    assert ramp["auto_break_minutes"] == 10
    assert format_hm(ramp["work_hours"]) == "4:00"

    full = span((8, 0), (13, 0))
    assert full["auto_break_minutes"] == 30
    assert format_hm(full["work_hours"]) == "4:30"
    assert "break_short" not in full["warnings"]

    nine = span((7, 0), (16, 46))
    assert nine["auto_break_minutes"] == 45

    raw = span((8, 0), (13, 0), auto=False)
    assert "break_short:30:4" in raw["warnings"]
    assert "break_short" not in raw["warnings"]

    only_four = _break_model([{"after_hours": 4, "minutes": 30}])
    long = summarize_day(
        [_p_on(day, "in", 7, 0), _p_on(day, "out", 17, 0)],
        day,
        only_four,
        now=now,
        auto_break=True,
    )
    assert long["auto_break_minutes"] == 30
    assert format_hm(long["work_hours"]) == "9:30"


def test_closed_month_without_break_rules_keeps_thirty_and_forty_five():
    from app.workmodels import overlay_model

    live = SimpleNamespace(
        id=1,
        name="Vollzeit",
        kind="flextime",
        hours_mon=8,
        hours_tue=8,
        hours_wed=8,
        hours_thu=8,
        hours_fri=8,
        hours_sat=0,
        hours_sun=0,
        round_start_before=0,
        round_start_after=0,
        round_end_before=0,
        round_end_after=0,
        round_first_threshold=0,
        round_first_step=0,
        round_last_threshold=0,
        round_last_step=0,
        booking_corridor="",
        shifts="",
        break_rules=json.dumps([{"after_hours": 4, "minutes": 30}]),
    )
    frozen = overlay_model(live, {"hours_mon": 8})
    day = date(2026, 9, 17)
    now = datetime(2026, 9, 18, tzinfo=ZoneInfo("UTC"))
    five = summarize_day(
        [_p_on(day, "in", 8, 0), _p_on(day, "out", 13, 0)],
        day,
        frozen,
        now=now,
        auto_break=True,
    )
    assert five["auto_break_minutes"] == 0
    seven = summarize_day(
        [_p_on(day, "in", 8, 0), _p_on(day, "out", 15, 30)],
        day,
        frozen,
        now=now,
        auto_break=True,
    )
    assert seven["auto_break_minutes"] == 30


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
