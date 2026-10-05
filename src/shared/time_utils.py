from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def parse_utc(value: object) -> datetime:
    """Parse an ISO-8601 value (or datetime) as an aware UTC datetime. Naive values are treated as UTC."""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_z(value: datetime) -> str:
    return parse_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def floor_minute(value: datetime) -> datetime:
    return parse_utc(value).replace(second=0, microsecond=0)


def floor_hour(value: datetime) -> datetime:
    return parse_utc(value).replace(minute=0, second=0, microsecond=0)


def from_unix(value: object) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def hour_range(start: datetime, end: datetime) -> list[datetime]:
    """Inclusive list of hour starts between start and end."""
    current = floor_hour(start)
    last = floor_hour(end)
    hours: list[datetime] = []
    while current <= last:
        hours.append(current)
        current += timedelta(hours=1)
    return hours


def to_local(value: datetime, utc_offset_seconds: int) -> datetime:
    """Return a naive local datetime for a fixed UTC offset (Brazil has no DST since 2019)."""
    return (parse_utc(value) + timedelta(seconds=utc_offset_seconds)).replace(tzinfo=None)


def local_date_of(value: datetime, utc_offset_seconds: int) -> date:
    return to_local(value, utc_offset_seconds).date()


def month_start(value: datetime) -> datetime:
    return parse_utc(value).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
