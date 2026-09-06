from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.datafox import ack_body, flatten_params, normalize_badge, parse_badge, parse_kind, parse_timestamp
from app.punches import booking_time


def test_badge_decimal_and_hex_match():
    n = 3974679390
    assert normalize_badge(str(n)) & normalize_badge(format(n, "X"))


def test_parse_kind_from_fn_and_labels():
    assert parse_kind({"df_col_fn": "1"}) == "in"
    assert parse_kind({"df_col_kind": "Gehen"}) == "out"
    assert parse_kind({"fn": "F3"}) == "break_start"
    assert parse_kind({"status": "pause_ende"}) == "break_end"


def test_parse_badge_prefers_named_field():
    params = flatten_params({"df_col_badge": "1234", "df_col_sn": "3569"})
    assert parse_badge(params) == "1234"


def test_parse_timestamp_naive_berlin():
    dt = parse_timestamp({"df_col_timestamp": "2026-09-04T22:15:00"})
    assert dt is not None
    assert dt.tzinfo is not None
    local = dt.astimezone(ZoneInfo("Europe/Berlin"))
    assert local.hour == 22


def test_ack_encodes_umlauts_as_latin1():
    body = ack_body({"df_msg": "nicht möglich,6,2,0"})
    assert "%C3%B6" not in body
    assert "%F6" in body or "möglich" in body


def test_booking_time_keeps_recent_device_time():
    now = datetime(2026, 9, 5, 8, 0, tzinfo=ZoneInfo("UTC"))
    device = now - timedelta(hours=10)
    assert booking_time(device, now) == device
    too_old = now - timedelta(days=5)
    assert booking_time(too_old, now) == now


def test_flatten_params_exposes_col_without_prefix():
    params = flatten_params({"df_col_badge": "AABB", "df_table": "Booking"})
    assert parse_badge(params) == "AABB"
    assert params["badge"] == "AABB"


def test_format_flex_uses_german_decimal():
    from app.balance import format_flex

    assert format_flex(2.5) == "+2,5h"
    assert format_flex(-1.0) == "-1,0h"
    assert format_flex(0) == "+0,0h"
