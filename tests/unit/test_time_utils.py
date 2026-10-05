from datetime import UTC, date, datetime

from shared.time_utils import floor_hour, from_unix, hour_range, iso_z, local_date_of, month_start, parse_utc, to_local


def test_parse_utc_treats_naive_values_as_utc() -> None:
    assert parse_utc("2026-06-25T12:30:00") == datetime(2026, 6, 25, 12, 30, tzinfo=UTC)
    assert parse_utc("2026-06-25T09:30:00-03:00") == datetime(2026, 6, 25, 12, 30, tzinfo=UTC)
    assert parse_utc(datetime(2026, 6, 25, 12, 30)) == datetime(2026, 6, 25, 12, 30, tzinfo=UTC)


def test_iso_and_floor_helpers() -> None:
    moment = datetime(2026, 6, 25, 12, 34, 56, 789, tzinfo=UTC)
    assert iso_z(moment) == "2026-06-25T12:34:56Z"
    assert floor_hour(moment) == datetime(2026, 6, 25, 12, tzinfo=UTC)
    assert month_start(moment) == datetime(2026, 6, 1, tzinfo=UTC)


def test_from_unix_handles_invalid_values() -> None:
    assert from_unix(0) == datetime(1970, 1, 1, tzinfo=UTC)
    assert from_unix(None) is None
    assert from_unix(True) is None
    assert from_unix("abc") is None


def test_hour_range_is_inclusive() -> None:
    hours = hour_range(datetime(2026, 6, 25, 22, 10, tzinfo=UTC), datetime(2026, 6, 26, 1, tzinfo=UTC))
    assert [hour.hour for hour in hours] == [22, 23, 0, 1]


def test_local_conversion_uses_fixed_offset() -> None:
    moment = datetime(2026, 6, 26, 2, tzinfo=UTC)
    assert to_local(moment, -3 * 3600) == datetime(2026, 6, 25, 23)
    assert local_date_of(moment, -3 * 3600) == date(2026, 6, 25)
