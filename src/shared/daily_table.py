from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pyarrow as pa

from shared.aggregation import maximum, mean, minimum, mode, total, values
from shared.capitals import BRAZIL_CAPITALS
from shared.parquet_io import records_to_parquet

DAILY_SCHEMA = pa.schema(
    [
        pa.field("observation_date", pa.date32()),
        pa.field("year", pa.int16()),
        pa.field("month", pa.int8()),
        pa.field("day", pa.int8()),
        pa.field("city", pa.string()),
        pa.field("state", pa.string()),
        pa.field("region", pa.string()),
        pa.field("ibge_code", pa.string()),
        pa.field("latitude", pa.float64()),
        pa.field("longitude", pa.float64()),
        pa.field("temperature_avg", pa.float64()),
        pa.field("temperature_min", pa.float64()),
        pa.field("temperature_max", pa.float64()),
        pa.field("temperature_amplitude", pa.float64()),
        pa.field("feels_like_avg", pa.float64()),
        pa.field("feels_like_max", pa.float64()),
        pa.field("humidity_avg", pa.float64()),
        pa.field("humidity_min", pa.float64()),
        pa.field("humidity_max", pa.float64()),
        pa.field("pressure_avg", pa.float64()),
        pa.field("wind_speed_avg", pa.float64()),
        pa.field("wind_speed_max", pa.float64()),
        pa.field("wind_gust_max", pa.float64()),
        pa.field("clouds_avg", pa.float64()),
        pa.field("visibility_avg", pa.float64()),
        pa.field("rain_mm", pa.float64()),
        pa.field("rain_hours", pa.int16()),
        pa.field("snow_mm", pa.float64()),
        pa.field("weather_main", pa.string()),
        pa.field("weather_description", pa.string()),
        pa.field("weather_icon", pa.string()),
        pa.field("sunrise", pa.timestamp("ms")),
        pa.field("sunset", pa.timestamp("ms")),
        pa.field("aqi_avg", pa.float64()),
        pa.field("aqi_max", pa.int8()),
        pa.field("pm2_5_avg", pa.float64()),
        pa.field("pm10_avg", pa.float64()),
        pa.field("o3_avg", pa.float64()),
        pa.field("no2_avg", pa.float64()),
        pa.field("so2_avg", pa.float64()),
        pa.field("co_avg", pa.float64()),
        pa.field("hours_observed", pa.int16()),
        pa.field("sample_count", pa.int32()),
        pa.field("processed_at", pa.timestamp("ms")),
    ]
)

_MIN_OFFSET = min(capital["utc_offset_seconds"] for capital in BRAZIL_CAPITALS)
_MAX_OFFSET = max(capital["utc_offset_seconds"] for capital in BRAZIL_CAPITALS)


def build_curated_daily_key(local_date: date) -> str:
    return f"curated/daily_observations/year={local_date:%Y}/month={local_date:%m}/day={local_date:%d}/weather_daily_observations_{local_date:%Y%m%d}.parquet"


def utc_hours_for_local_date(local_date: date) -> list[datetime]:
    """UTC hour starts that may hold rows whose local_date is `local_date` for any capital."""
    midnight = datetime.combine(local_date, time(0), tzinfo=UTC)
    first = midnight - timedelta(seconds=_MAX_OFFSET)
    last = midnight + timedelta(days=1) - timedelta(seconds=_MIN_OFFSET) - timedelta(hours=1)
    hours: list[datetime] = []
    current = first
    while current <= last:
        hours.append(current)
        current += timedelta(hours=1)
    return hours


def local_day_is_closed(local_date: date, now: datetime) -> bool:
    """True once the last UTC hour of the local day (westernmost capital) has itself closed."""
    return now >= utc_hours_for_local_date(local_date)[-1] + timedelta(hours=1)


def aggregate_daily(hourly_records: list[dict[str, Any]], local_date: date, processed_at: datetime | None = None) -> list[dict[str, Any]]:
    processed_at = processed_at or datetime.now(UTC).replace(microsecond=0)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in hourly_records:
        if record.get("local_date") == local_date:
            groups[str(record["state"])].append(record)

    records: list[dict[str, Any]] = []
    for state in sorted(groups):
        rows = sorted(groups[state], key=lambda row: row["observation_timestamp"])
        weather_rows = [row for row in rows if row.get("temperature_avg") is not None]
        temp_min = minimum(values(rows, "temperature_min"))
        temp_max = maximum(values(rows, "temperature_max"))
        aqi_max = maximum(values(rows, "aqi"))
        rain = values(rows, "rain_mm")
        first = rows[0]
        last_with_sun = next((row for row in reversed(rows) if row.get("sunrise")), {})
        daytime_rows = [row for row in weather_rows if str(row.get("weather_icon") or "").endswith("d")] or weather_rows
        records.append(
            {
                "observation_date": local_date,
                "year": local_date.year,
                "month": local_date.month,
                "day": local_date.day,
                "city": first["city"],
                "state": state,
                "region": first.get("region"),
                "ibge_code": first.get("ibge_code"),
                "latitude": first.get("latitude"),
                "longitude": first.get("longitude"),
                "temperature_avg": mean(values(rows, "temperature_avg")),
                "temperature_min": temp_min,
                "temperature_max": temp_max,
                "temperature_amplitude": round(temp_max - temp_min, 2) if temp_min is not None and temp_max is not None else None,
                "feels_like_avg": mean(values(rows, "feels_like_avg")),
                "feels_like_max": maximum(values(rows, "feels_like_avg")),
                "humidity_avg": mean(values(rows, "humidity_avg")),
                "humidity_min": minimum(values(rows, "humidity_min")),
                "humidity_max": maximum(values(rows, "humidity_max")),
                "pressure_avg": mean(values(rows, "pressure_avg")),
                "wind_speed_avg": mean(values(rows, "wind_speed_avg")),
                "wind_speed_max": maximum(values(rows, "wind_speed_max")),
                "wind_gust_max": maximum(values(rows, "wind_gust_max")),
                "clouds_avg": mean(values(rows, "clouds_avg")),
                "visibility_avg": mean(values(rows, "visibility_avg")),
                "rain_mm": total(rain),
                "rain_hours": sum(1 for value in rain if value > 0),
                "snow_mm": total(values(rows, "snow_mm")),
                "weather_main": mode([row.get("weather_main") for row in daytime_rows]),
                "weather_description": mode([row.get("weather_description") for row in daytime_rows]),
                "weather_icon": mode([row.get("weather_icon") for row in daytime_rows]),
                "sunrise": last_with_sun.get("sunrise"),
                "sunset": last_with_sun.get("sunset"),
                "aqi_avg": mean(values(rows, "aqi"), 2),
                "aqi_max": int(aqi_max) if aqi_max is not None else None,
                "pm2_5_avg": mean(values(rows, "pm2_5"), 3),
                "pm10_avg": mean(values(rows, "pm10"), 3),
                "o3_avg": mean(values(rows, "o3"), 3),
                "no2_avg": mean(values(rows, "no2"), 3),
                "so2_avg": mean(values(rows, "so2"), 3),
                "co_avg": mean(values(rows, "co"), 3),
                "hours_observed": len(weather_rows),
                "sample_count": sum(int(row.get("sample_count") or 0) for row in rows),
                "processed_at": processed_at,
            }
        )
    return records


def daily_records_to_parquet(records: list[dict[str, Any]]) -> bytes:
    return records_to_parquet(records, DAILY_SCHEMA)
