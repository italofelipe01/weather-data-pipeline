from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pyarrow as pa

from shared.parquet_io import records_to_parquet
from shared.time_utils import floor_hour, to_local

FORECAST_SCHEMA = pa.schema(
    [
        pa.field("issued_at", pa.timestamp("ms")),
        pa.field("forecast_time", pa.timestamp("ms")),
        pa.field("forecast_date", pa.date32()),
        pa.field("forecast_hour", pa.int16()),
        pa.field("local_forecast_date", pa.date32()),
        pa.field("local_forecast_hour", pa.int16()),
        pa.field("lead_hours", pa.float64()),
        pa.field("year", pa.int16()),
        pa.field("month", pa.int8()),
        pa.field("day", pa.int8()),
        pa.field("city", pa.string()),
        pa.field("state", pa.string()),
        pa.field("region", pa.string()),
        pa.field("ibge_code", pa.string()),
        pa.field("latitude", pa.float64()),
        pa.field("longitude", pa.float64()),
        pa.field("temperature", pa.float64()),
        pa.field("feels_like", pa.float64()),
        pa.field("temperature_min", pa.float64()),
        pa.field("temperature_max", pa.float64()),
        pa.field("humidity", pa.float64()),
        pa.field("pressure", pa.float64()),
        pa.field("sea_level_pressure", pa.float64()),
        pa.field("ground_level_pressure", pa.float64()),
        pa.field("clouds", pa.float64()),
        pa.field("wind_speed", pa.float64()),
        pa.field("wind_deg", pa.float64()),
        pa.field("wind_gust", pa.float64()),
        pa.field("visibility", pa.float64()),
        pa.field("pop", pa.float64()),
        pa.field("rain_3h_mm", pa.float64()),
        pa.field("snow_3h_mm", pa.float64()),
        pa.field("weather_id", pa.int32()),
        pa.field("weather_main", pa.string()),
        pa.field("weather_description", pa.string()),
        pa.field("weather_icon", pa.string()),
        pa.field("part_of_day", pa.string()),
        pa.field("city_population", pa.int64()),
        pa.field("processed_at", pa.timestamp("ms")),
    ]
)


def build_curated_forecast_key(issue_hour: datetime) -> str:
    hour = floor_hour(issue_hour)
    return f"curated/forecast_3h/year={hour:%Y}/month={hour:%m}/day={hour:%d}/hour={hour:%H}/weather_forecast_3h_{hour:%Y%m%dT%H00Z}.parquet"


def latest_per_state(extracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for extract in extracts:
        current = latest.get(extract["state"])
        if current is None or extract["issued_at"] > current["issued_at"]:
            latest[extract["state"]] = extract
    return [latest[state] for state in sorted(latest)]


def build_forecast_records(extracts: list[dict[str, Any]], processed_at: datetime | None = None) -> list[dict[str, Any]]:
    processed_at = processed_at or datetime.now(UTC).replace(microsecond=0)
    records: list[dict[str, Any]] = []
    for extract in latest_per_state(extracts):
        issued_at: datetime = extract["issued_at"]
        offset = int(extract.get("utc_offset_seconds") or 0)
        for item in extract["items"]:
            forecast_time: datetime = item["forecast_time"]
            local = to_local(forecast_time, offset)
            records.append(
                {
                    "issued_at": issued_at,
                    "forecast_time": forecast_time,
                    "forecast_date": forecast_time.date(),
                    "forecast_hour": forecast_time.hour,
                    "local_forecast_date": local.date(),
                    "local_forecast_hour": local.hour,
                    "lead_hours": round((forecast_time - issued_at).total_seconds() / 3600, 2),
                    "year": issued_at.year,
                    "month": issued_at.month,
                    "day": issued_at.day,
                    "city": extract["city"],
                    "state": extract["state"],
                    "region": extract.get("region"),
                    "ibge_code": extract.get("ibge_code"),
                    "latitude": extract.get("latitude"),
                    "longitude": extract.get("longitude"),
                    "temperature": item.get("temperature"),
                    "feels_like": item.get("feels_like"),
                    "temperature_min": item.get("temp_min"),
                    "temperature_max": item.get("temp_max"),
                    "humidity": item.get("humidity"),
                    "pressure": item.get("pressure"),
                    "sea_level_pressure": item.get("sea_level"),
                    "ground_level_pressure": item.get("grnd_level"),
                    "clouds": item.get("clouds"),
                    "wind_speed": item.get("wind_speed"),
                    "wind_deg": item.get("wind_deg"),
                    "wind_gust": item.get("wind_gust"),
                    "visibility": item.get("visibility"),
                    "pop": item.get("pop"),
                    "rain_3h_mm": item.get("rain_3h"),
                    "snow_3h_mm": item.get("snow_3h"),
                    "weather_id": item.get("weather_id"),
                    "weather_main": item.get("weather_main"),
                    "weather_description": item.get("weather_description"),
                    "weather_icon": item.get("weather_icon"),
                    "part_of_day": item.get("part_of_day"),
                    "city_population": extract.get("city_population"),
                    "processed_at": processed_at,
                }
            )
    return records


def forecast_records_to_parquet(records: list[dict[str, Any]]) -> bytes:
    return records_to_parquet(records, FORECAST_SCHEMA)
