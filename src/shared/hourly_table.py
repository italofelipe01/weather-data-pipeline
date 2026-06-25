from __future__ import annotations

import csv
import io
import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

HOURLY_FIELDNAMES = [
    "observation_date",
    "observation_hour",
    "observation_timestamp",
    "year",
    "month",
    "day",
    "city",
    "state",
    "ibge_code",
    "latitude",
    "longitude",
    "temperature_avg",
    "temperature_min",
    "temperature_max",
    "feels_like_avg",
    "humidity_avg",
    "pressure_avg",
    "wind_speed_avg",
    "clouds_avg",
    "rain_1h_sum",
    "sample_count",
    "source_product",
    "processed_at",
]


def parse_target_hour(value: object | None = None) -> datetime:
    if value:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
        return parsed.replace(minute=0, second=0, microsecond=0)
    return (datetime.now(UTC) - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)


def build_raw_hour_prefix(target_hour: datetime) -> str:
    hour = target_hour.astimezone(UTC)
    return f"raw/source=openweather-free-plan/product=current_weather/year={hour:%Y}/month={hour:%m}/day={hour:%d}/hour={hour:%H}/"


def build_curated_hourly_key(target_hour: datetime) -> str:
    hour = target_hour.astimezone(UTC)
    timestamp = hour.strftime("%Y%m%dT%H00Z")
    return f"curated/hourly_observations/year={hour:%Y}/month={hour:%m}/day={hour:%d}/hour={hour:%H}/weather_hourly_observations_{timestamp}.csv"


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.fmean(values), 4)


def extract_current_weather_sample(source_object: dict[str, Any]) -> dict[str, Any] | None:
    job = source_object.get("job")
    response = source_object.get("response")
    if not isinstance(job, dict) or not isinstance(response, dict):
        return None
    if job.get("product") != "current_weather":
        return None

    snapshot_at = datetime.fromisoformat(str(job["snapshot_at"]).replace("Z", "+00:00")).astimezone(UTC)
    main = response.get("main") if isinstance(response.get("main"), dict) else {}
    wind = response.get("wind") if isinstance(response.get("wind"), dict) else {}
    clouds = response.get("clouds") if isinstance(response.get("clouds"), dict) else {}
    rain = response.get("rain") if isinstance(response.get("rain"), dict) else {}

    return {
        "observation_timestamp": snapshot_at.replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z"),
        "observation_hour_start": snapshot_at.replace(minute=0, second=0, microsecond=0),
        "city": str(job["city"]),
        "state": str(job["state"]),
        "ibge_code": str(job["ibge_code"]),
        "latitude": _as_float(job.get("latitude")),
        "longitude": _as_float(job.get("longitude")),
        "temperature": _as_float(main.get("temp")),
        "temperature_min": _as_float(main.get("temp_min")),
        "temperature_max": _as_float(main.get("temp_max")),
        "feels_like": _as_float(main.get("feels_like")),
        "humidity": _as_float(main.get("humidity")),
        "pressure": _as_float(main.get("pressure")),
        "wind_speed": _as_float(wind.get("speed")),
        "clouds": _as_float(clouds.get("all")),
        "rain_1h": _as_float(rain.get("1h")) or 0.0,
    }


def aggregate_hourly(samples: list[dict[str, Any]], processed_at: str | None = None) -> list[dict[str, Any]]:
    if processed_at is None:
        processed_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    groups: dict[tuple[str, str, datetime], list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        groups[(str(sample["state"]), str(sample["city"]), sample["observation_hour_start"])].append(sample)

    records: list[dict[str, Any]] = []
    for (_state, _city, hour), rows in sorted(groups.items(), key=lambda item: (item[0][2], item[0][0], item[0][1])):
        first = rows[0]
        temps = [value for row in rows if (value := row["temperature"]) is not None]
        temp_mins = [value for row in rows if (value := row["temperature_min"]) is not None]
        temp_maxs = [value for row in rows if (value := row["temperature_max"]) is not None]
        record = {
            "observation_date": hour.date().isoformat(),
            "observation_hour": hour.hour,
            "observation_timestamp": hour.isoformat().replace("+00:00", "Z"),
            "year": hour.year,
            "month": hour.month,
            "day": hour.day,
            "city": first["city"],
            "state": first["state"],
            "ibge_code": first["ibge_code"],
            "latitude": first["latitude"],
            "longitude": first["longitude"],
            "temperature_avg": _avg(temps),
            "temperature_min": min(temp_mins) if temp_mins else None,
            "temperature_max": max(temp_maxs) if temp_maxs else None,
            "feels_like_avg": _avg([value for row in rows if (value := row["feels_like"]) is not None]),
            "humidity_avg": _avg([value for row in rows if (value := row["humidity"]) is not None]),
            "pressure_avg": _avg([value for row in rows if (value := row["pressure"]) is not None]),
            "wind_speed_avg": _avg([value for row in rows if (value := row["wind_speed"]) is not None]),
            "clouds_avg": _avg([value for row in rows if (value := row["clouds"]) is not None]),
            "rain_1h_sum": round(sum(row["rain_1h"] for row in rows), 4),
            "sample_count": len(rows),
            "source_product": "current_weather",
            "processed_at": processed_at,
        }
        records.append(record)
    return records


def records_to_csv(records: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=HOURLY_FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow({field: "" if record.get(field) is None else record.get(field) for field in HOURLY_FIELDNAMES})
    return buffer.getvalue()
