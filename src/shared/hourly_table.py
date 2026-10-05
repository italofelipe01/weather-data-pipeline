from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import pyarrow as pa

from shared.aggregation import circular_mean_deg, maximum, mean, minimum, mode, values
from shared.capitals import capital_by_state
from shared.observations import AIR_COMPONENTS, observation_hour
from shared.parquet_io import records_to_parquet as _records_to_parquet
from shared.storage import build_raw_hour_prefix as _build_raw_hour_prefix
from shared.time_utils import floor_hour, parse_utc, to_local

HOURLY_SCHEMA = pa.schema(
    [
        pa.field("observation_date", pa.date32()),
        pa.field("observation_hour", pa.int16()),
        pa.field("observation_timestamp", pa.timestamp("ms")),
        pa.field("year", pa.int16()),
        pa.field("month", pa.int8()),
        pa.field("day", pa.int8()),
        pa.field("local_date", pa.date32()),
        pa.field("local_hour", pa.int16()),
        pa.field("city", pa.string()),
        pa.field("state", pa.string()),
        pa.field("region", pa.string()),
        pa.field("ibge_code", pa.string()),
        pa.field("latitude", pa.float64()),
        pa.field("longitude", pa.float64()),
        pa.field("temperature_avg", pa.float64()),
        pa.field("temperature_min", pa.float64()),
        pa.field("temperature_max", pa.float64()),
        pa.field("feels_like_avg", pa.float64()),
        pa.field("humidity_avg", pa.float64()),
        pa.field("humidity_min", pa.float64()),
        pa.field("humidity_max", pa.float64()),
        pa.field("pressure_avg", pa.float64()),
        pa.field("sea_level_pressure_avg", pa.float64()),
        pa.field("ground_level_pressure_avg", pa.float64()),
        pa.field("wind_speed_avg", pa.float64()),
        pa.field("wind_speed_max", pa.float64()),
        pa.field("wind_gust_max", pa.float64()),
        pa.field("wind_deg_avg", pa.float64()),
        pa.field("clouds_avg", pa.float64()),
        pa.field("visibility_avg", pa.float64()),
        pa.field("rain_mm", pa.float64()),
        pa.field("rain_rate_max", pa.float64()),
        pa.field("snow_mm", pa.float64()),
        pa.field("weather_id", pa.int32()),
        pa.field("weather_main", pa.string()),
        pa.field("weather_description", pa.string()),
        pa.field("weather_icon", pa.string()),
        pa.field("sunrise", pa.timestamp("ms")),
        pa.field("sunset", pa.timestamp("ms")),
        pa.field("aqi", pa.int8()),
        *[pa.field(component, pa.float64()) for component in AIR_COMPONENTS],
        pa.field("sample_count", pa.int16()),
        pa.field("observation_count", pa.int16()),
        pa.field("air_sample_count", pa.int16()),
        pa.field("source_product", pa.string()),
        pa.field("processed_at", pa.timestamp("ms")),
    ]
)


def parse_target_hour(value: object | None = None, now: datetime | None = None) -> datetime:
    """Explicit hour (rounded down) or, by default, the last closed hour."""
    if value:
        return floor_hour(parse_utc(value))
    return floor_hour((now or datetime.now(UTC)) - timedelta(hours=1))


def build_raw_hour_prefix(target_hour: datetime, product: str = "current_weather") -> str:
    return _build_raw_hour_prefix(product, target_hour)


def build_curated_hourly_key(target_hour: datetime) -> str:
    hour = floor_hour(target_hour)
    return f"curated/hourly_observations/year={hour:%Y}/month={hour:%m}/day={hour:%d}/hour={hour:%H}/weather_hourly_observations_{hour:%Y%m%dT%H00Z}.parquet"


def _distinct_observations(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OpenWeather refreshes current data roughly every 10 minutes; repeated `dt` values must count once."""
    by_observation: dict[datetime, dict[str, Any]] = {}
    for sample in sorted(samples, key=lambda item: item["snapshot_at"]):
        by_observation[sample["observed_at"]] = sample
    return [by_observation[key] for key in sorted(by_observation)]


def _weather_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _distinct_observations(samples)
    temperatures = values(rows, "temperature")
    humidity = values(rows, "humidity")
    rain_rates = [row.get("rain_1h") or 0.0 for row in rows]
    snow_rates = [row.get("snow_1h") or 0.0 for row in rows]
    latest = rows[-1] if rows else {}
    return {
        "temperature_avg": mean(temperatures),
        "temperature_min": minimum(temperatures),
        "temperature_max": maximum(temperatures),
        "feels_like_avg": mean(values(rows, "feels_like")),
        "humidity_avg": mean(humidity),
        "humidity_min": minimum(humidity),
        "humidity_max": maximum(humidity),
        "pressure_avg": mean(values(rows, "pressure")),
        "sea_level_pressure_avg": mean(values(rows, "sea_level")),
        "ground_level_pressure_avg": mean(values(rows, "grnd_level")),
        "wind_speed_avg": mean(values(rows, "wind_speed")),
        "wind_speed_max": maximum(values(rows, "wind_speed")),
        "wind_gust_max": maximum(values(rows, "wind_gust")),
        "wind_deg_avg": circular_mean_deg(values(rows, "wind_deg")),
        "clouds_avg": mean(values(rows, "clouds")),
        "visibility_avg": mean(values(rows, "visibility")),
        # Mean intensity (mm/h) over one hour is the precipitation accumulated in that hour (mm).
        "rain_mm": mean(rain_rates) if rows else None,
        "rain_rate_max": maximum(rain_rates),
        "snow_mm": mean(snow_rates) if rows else None,
        "weather_id": mode([row.get("weather_id") for row in rows]),
        "weather_main": mode([row.get("weather_main") for row in rows]),
        "weather_description": mode([row.get("weather_description") for row in rows]),
        "weather_icon": mode([row.get("weather_icon") for row in rows]),
        "sunrise": latest.get("sunrise"),
        "sunset": latest.get("sunset"),
        "sample_count": len(samples),
        "observation_count": len(rows),
    }


def _air_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    aqi_values = [int(value) for row in samples if (value := row.get("aqi")) is not None]
    return {
        "aqi": max(aqi_values) if aqi_values else None,
        **{component: mean(values(samples, component), 3) for component in AIR_COMPONENTS},
        "air_sample_count": len(samples),
    }


def aggregate_hourly(
    weather_samples: list[dict[str, Any]],
    air_samples: list[dict[str, Any]] | None = None,
    processed_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """One row per capital per hour, merging current weather and air pollution snapshots of that hour."""
    processed_at = processed_at or datetime.now(UTC).replace(microsecond=0)
    weather_groups: dict[tuple[str, datetime], list[dict[str, Any]]] = defaultdict(list)
    air_groups: dict[tuple[str, datetime], list[dict[str, Any]]] = defaultdict(list)
    for sample in weather_samples:
        weather_groups[(sample["state"], observation_hour(sample))].append(sample)
    for sample in air_samples or []:
        air_groups[(sample["state"], observation_hour(sample))].append(sample)

    records: list[dict[str, Any]] = []
    for state, hour in sorted(set(weather_groups) | set(air_groups), key=lambda item: (item[1], item[0])):
        weather = weather_groups.get((state, hour), [])
        air = air_groups.get((state, hour), [])
        first = (weather or air)[0]
        capital = capital_by_state(state)
        offset = first.get("utc_offset_seconds") if first.get("utc_offset_seconds") is not None else (capital or {}).get("utc_offset_seconds", 0)
        local = to_local(hour, int(offset))
        record: dict[str, Any] = {
            "observation_date": hour.date(),
            "observation_hour": hour.hour,
            "observation_timestamp": hour,
            "year": hour.year,
            "month": hour.month,
            "day": hour.day,
            "local_date": local.date(),
            "local_hour": local.hour,
            "city": first["city"],
            "state": state,
            "region": first.get("region"),
            "ibge_code": first.get("ibge_code"),
            "latitude": first.get("latitude"),
            "longitude": first.get("longitude"),
            "source_product": "current_weather",
            "processed_at": processed_at,
        }
        record.update(_weather_metrics(weather))
        record.update(_air_metrics(air))
        records.append(record)
    return records


def normalize_hourly_record(record: dict[str, Any]) -> dict[str, Any]:
    """Fill columns missing from files written by the first schema version (no local time, rain summed per snapshot)."""
    capital = capital_by_state(str(record.get("state", "")))
    if record.get("local_date") is None and record.get("observation_timestamp") is not None:
        local = to_local(record["observation_timestamp"], capital["utc_offset_seconds"] if capital else 0)
        record["local_date"] = local.date()
        record["local_hour"] = local.hour
    if record.get("region") is None and capital:
        record["region"] = capital["region"]
    if "rain_mm" not in record and record.get("rain_1h_sum") is not None:
        samples = int(record.get("sample_count") or 0)
        record["rain_mm"] = round(float(record["rain_1h_sum"]) / samples, 4) if samples else None
    return record


def records_to_parquet(records: list[dict[str, Any]]) -> bytes:
    return _records_to_parquet(records, HOURLY_SCHEMA)
