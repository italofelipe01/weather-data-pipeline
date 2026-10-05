"""JSON documents consumed by the static frontend (served from the site bucket under `data/`).

Must not import pyarrow: the Publisher Lambda ships without the analytics layer.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from shared.capitals import BRAZIL_CAPITALS, Capital
from shared.time_utils import iso_z

SCHEMA_VERSION = 1
DATA_PREFIX = "data/"
LATEST_KEY = f"{DATA_PREFIX}latest.json"
LATEST_CACHE_CONTROL = "public, max-age=60"
SERIES_CACHE_CONTROL = "public, max-age=300"

ATTRIBUTION = "Dados meteorologicos: OpenWeather (openweathermap.org), plano Free."

CURRENT_FIELDS = (
    "observed_at",
    "snapshot_at",
    "temperature",
    "feels_like",
    "temp_min",
    "temp_max",
    "humidity",
    "pressure",
    "sea_level",
    "grnd_level",
    "visibility",
    "wind_speed",
    "wind_deg",
    "wind_gust",
    "clouds",
    "rain_1h",
    "snow_1h",
    "weather_id",
    "weather_main",
    "weather_description",
    "weather_icon",
    "sunrise",
    "sunset",
    "station_name",
)
AIR_FIELDS = ("observed_at", "aqi", "co", "no", "no2", "o3", "so2", "pm2_5", "pm10", "nh3")
HOURLY_FIELDS = (
    "observation_timestamp",
    "local_date",
    "local_hour",
    "temperature_avg",
    "temperature_min",
    "temperature_max",
    "feels_like_avg",
    "humidity_avg",
    "pressure_avg",
    "wind_speed_avg",
    "wind_gust_max",
    "wind_deg_avg",
    "clouds_avg",
    "visibility_avg",
    "rain_mm",
    "snow_mm",
    "weather_main",
    "weather_description",
    "weather_icon",
    "aqi",
    "pm2_5",
    "pm10",
    "o3",
    "no2",
    "observation_count",
)
DAILY_FIELDS = (
    "observation_date",
    "temperature_avg",
    "temperature_min",
    "temperature_max",
    "temperature_amplitude",
    "feels_like_max",
    "humidity_avg",
    "humidity_min",
    "humidity_max",
    "pressure_avg",
    "wind_speed_avg",
    "wind_gust_max",
    "clouds_avg",
    "rain_mm",
    "rain_hours",
    "weather_main",
    "weather_description",
    "weather_icon",
    "sunrise",
    "sunset",
    "aqi_avg",
    "aqi_max",
    "pm2_5_avg",
    "pm10_avg",
    "hours_observed",
)
FORECAST_FIELDS = (
    "forecast_time",
    "temperature",
    "feels_like",
    "temp_min",
    "temp_max",
    "humidity",
    "pressure",
    "clouds",
    "wind_speed",
    "wind_deg",
    "wind_gust",
    "visibility",
    "pop",
    "rain_3h",
    "snow_3h",
    "weather_id",
    "weather_main",
    "weather_description",
    "weather_icon",
    "part_of_day",
)
AIR_FORECAST_FIELDS = ("forecast_time", "aqi", "pm2_5", "pm10", "o3", "no2", "so2", "co")


def hourly_key(state: str) -> str:
    return f"{DATA_PREFIX}hourly/{state.lower()}.json"


def daily_key(state: str) -> str:
    return f"{DATA_PREFIX}daily/{state.lower()}.json"


def forecast_key(state: str) -> str:
    return f"{DATA_PREFIX}forecast/{state.lower()}.json"


def json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return iso_z(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else round(value, 4)
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_value(item) for item in value]
    return value


def pick(record: dict[str, Any] | None, fields: Iterable[str]) -> dict[str, Any] | None:
    if record is None:
        return None
    return {field: json_value(record.get(field)) for field in fields}


def capital_info(capital: Capital) -> dict[str, Any]:
    return {
        "state": capital["state"],
        "city": capital["city"],
        "name": capital["display_name"],
        "region": capital["region"],
        "ibge_code": capital["ibge_code"],
        "latitude": capital["latitude"],
        "longitude": capital["longitude"],
        "timezone": capital["timezone"],
        "utc_offset_seconds": capital["utc_offset_seconds"],
    }


def build_latest_payload(
    current_by_state: dict[str, dict[str, Any]],
    air_by_state: dict[str, dict[str, Any]],
    generated_at: datetime,
    budget: dict[str, Any] | None = None,
    previous: dict[str, Any] | None = None,
    products: list[str] | None = None,
) -> dict[str, Any]:
    """Latest observation per capital. Capitals missing from this run keep their previous values."""
    previous_by_state = {item.get("state"): item for item in (previous or {}).get("capitals", []) if isinstance(item, dict)}
    capitals: list[dict[str, Any]] = []
    for capital in BRAZIL_CAPITALS:
        state = capital["state"]
        old = previous_by_state.get(state, {})
        current = pick(current_by_state.get(state), CURRENT_FIELDS) or old.get("current")
        air = pick(air_by_state.get(state), AIR_FIELDS) or old.get("air")
        capitals.append({**capital_info(capital), "current": current, "air": air})
    observed = [item["current"]["observed_at"] for item in capitals if item["current"] and item["current"].get("observed_at")]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_z(generated_at),
        "latest_observation_at": max(observed) if observed else None,
        "attribution": ATTRIBUTION,
        "products": products or [],
        "budget": budget,
        "capitals": capitals,
    }


def build_hourly_payload(capital: Capital, records: list[dict[str, Any]], generated_at: datetime, days: int) -> dict[str, Any]:
    rows = sorted(records, key=lambda row: row["observation_timestamp"])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_z(generated_at),
        "window_days": days,
        "capital": capital_info(capital),
        "rows": [pick(row, HOURLY_FIELDS) for row in rows],
    }


def merge_daily_rows(existing: list[dict[str, Any]], updates: list[dict[str, Any]], max_days: int) -> list[dict[str, Any]]:
    by_date = {str(row["observation_date"]): row for row in existing if row.get("observation_date")}
    for row in updates:
        by_date[str(row["observation_date"])] = row
    ordered = [by_date[key] for key in sorted(by_date)]
    return ordered[-max_days:] if max_days > 0 else ordered


def build_daily_payload(capital: Capital, rows: list[dict[str, Any]], generated_at: datetime, max_days: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_z(generated_at),
        "max_days": max_days,
        "capital": capital_info(capital),
        "rows": rows,
    }


def daily_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in (pick(record, DAILY_FIELDS) for record in records) if row is not None]


def build_forecast_payload(
    capital: Capital,
    forecast: dict[str, Any] | None,
    air_forecast: dict[str, Any] | None,
    generated_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_z(generated_at),
        "capital": capital_info(capital),
        "weather": {
            "issued_at": json_value(forecast["issued_at"]),
            "city_population": forecast.get("city_population"),
            "sunrise": json_value(forecast.get("sunrise")),
            "sunset": json_value(forecast.get("sunset")),
            "items": [pick(item, FORECAST_FIELDS) for item in forecast["items"]],
        }
        if forecast
        else None,
        "air": {
            "issued_at": json_value(air_forecast["issued_at"]),
            "items": [pick(item, AIR_FORECAST_FIELDS) for item in air_forecast["items"]],
        }
        if air_forecast
        else None,
    }
