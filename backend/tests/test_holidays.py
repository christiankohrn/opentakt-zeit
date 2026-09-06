from datetime import date

from app.holidays import easter, public_holidays


def test_easter_2026():
    assert easter(2026) == date(2026, 4, 5)


def test_nw_holidays_2026():
    days = public_holidays(2026, "NW")
    assert days[date(2026, 1, 1)] == "Neujahr"
    assert days[date(2026, 4, 3)] == "Karfreitag"
    assert days[date(2026, 4, 6)] == "Ostermontag"
    assert days[date(2026, 5, 14)] == "Christi Himmelfahrt"
    assert days[date(2026, 5, 25)] == "Pfingstmontag"
    assert days[date(2026, 6, 4)] == "Fronleichnam"
    assert days[date(2026, 10, 3)] == "Tag der Deutschen Einheit"
    assert days[date(2026, 11, 1)] == "Allerheiligen"
    assert date(2026, 10, 31) not in days
    assert date(2026, 1, 6) not in days


def test_by_has_epiphany_nw_does_not():
    assert date(2026, 1, 6) in public_holidays(2026, "BY")
    assert date(2026, 1, 6) not in public_holidays(2026, "NW")
