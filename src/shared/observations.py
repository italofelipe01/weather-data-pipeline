"""Flatten raw OpenWeather snapshots (as stored by the Collector) into typed Python dictionaries.

These helpers are shared by the Curator (Parquet tables) and the Publisher (frontend JSON) and must not import pyarrow.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared.capitals import capital_by_state
from shared.time_utils import from_unix, parse_utc

AIR_COMPONENTS = ("co", "no", "no2", "o3", "so2", "pm2_5", "pm10", "nh3")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    return int(number) if number is not None else None


def _first_weather(record: dict[str, Any]) -> dict[str, Any]:
    weather = record.get("weather")
    if isinstance(weather, list) and weather and isinstance(weather[0], dict):
        return weather[0]
    return {}


def job_context(source_object: dict[str, Any], product: str) -> dict[str, Any] | None:
    job = source_object.get("job")
    response = source_object.get("response")
    if not isinstance(job, dict) or not isinstance(response, dict) or job.get("product") != product:
        return None
    state = str(job.get("state", "")).upper()
    capital = capital_by_state(state)
    return {
        "snapshot_at": parse_utc(job["snapshot_at"]),
        "state": state,
        "city": str(job.get("city") or (capital["city"] if capital else "")),
        "display_name": capital["display_name"] if capital else str(job.get("city", "")),
        "region": capital["region"] if capital else None,
        "ibge_code": str(job.get("ibge_code") or (capital["ibge_code"] if capital else "")),
        "latitude": as_float(job.get("latitude")),
        "longitude": as_float(job.get("longitude")),
        "utc_offset_seconds": capital["utc_offset_seconds"] if capital else as_int(response.get("timezone")) or 0,
    }


def _weather_fields(record: dict[str, Any]) -> dict[str, Any]:
    weather = _first_weather(record)
    return {
        "weather_id": as_int(weather.get("id")),
        "weather_main": weather.get("main"),
        "weather_description": weather.get("description"),
        "weather_icon": weather.get("icon"),
    }


def extract_current_weather(source_object: dict[str, Any]) -> dict[str, Any] | None:
    context = job_context(source_object, "current_weather")
    if context is None:
        return None
    response = source_object["response"]
    main = _dict(response.get("main"))
    wind = _dict(response.get("wind"))
    sys_info = _dict(response.get("sys"))
    return {
        **context,
        "observed_at": from_unix(response.get("dt")) or context["snapshot_at"],
        "temperature": as_float(main.get("temp")),
        "feels_like": as_float(main.get("feels_like")),
        "temp_min": as_float(main.get("temp_min")),
        "temp_max": as_float(main.get("temp_max")),
        "humidity": as_float(main.get("humidity")),
        "pressure": as_float(main.get("pressure")),
        "sea_level": as_float(main.get("sea_level")),
        "grnd_level": as_float(main.get("grnd_level")),
        "visibility": as_float(response.get("visibility")),
        "wind_speed": as_float(wind.get("speed")),
        "wind_deg": as_float(wind.get("deg")),
        "wind_gust": as_float(wind.get("gust")),
        "clouds": as_float(_dict(response.get("clouds")).get("all")),
        # OpenWeather documents rain.1h / snow.1h as an intensity in mm/h; absence means no precipitation.
        "rain_1h": as_float(_dict(response.get("rain")).get("1h")) or 0.0,
        "snow_1h": as_float(_dict(response.get("snow")).get("1h")) or 0.0,
        **_weather_fields(response),
        "sunrise": from_unix(sys_info.get("sunrise")),
        "sunset": from_unix(sys_info.get("sunset")),
        "station_name": response.get("name"),
    }


def _air_fields(record: dict[str, Any]) -> dict[str, Any]:
    components = _dict(record.get("components"))
    return {
        "aqi": as_int(_dict(record.get("main")).get("aqi")),
        **{component: as_float(components.get(component)) for component in AIR_COMPONENTS},
    }


def extract_air_pollution(source_object: dict[str, Any]) -> dict[str, Any] | None:
    context = job_context(source_object, "air_pollution")
    if context is None:
        return None
    records = source_object["response"].get("list")
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        return None
    record = records[0]
    return {**context, "observed_at": from_unix(record.get("dt")) or context["snapshot_at"], **_air_fields(record)}


def extract_forecast(source_object: dict[str, Any]) -> dict[str, Any] | None:
    context = job_context(source_object, "forecast_5d_3h")
    if context is None:
        return None
    response = source_object["response"]
    city = _dict(response.get("city"))
    items: list[dict[str, Any]] = []
    for record in response.get("list") or []:
        if not isinstance(record, dict) or from_unix(record.get("dt")) is None:
            continue
        main = _dict(record.get("main"))
        wind = _dict(record.get("wind"))
        items.append(
            {
                "forecast_time": from_unix(record.get("dt")),
                "temperature": as_float(main.get("temp")),
                "feels_like": as_float(main.get("feels_like")),
                "temp_min": as_float(main.get("temp_min")),
                "temp_max": as_float(main.get("temp_max")),
                "humidity": as_float(main.get("humidity")),
                "pressure": as_float(main.get("pressure")),
                "sea_level": as_float(main.get("sea_level")),
                "grnd_level": as_float(main.get("grnd_level")),
                "clouds": as_float(_dict(record.get("clouds")).get("all")),
                "wind_speed": as_float(wind.get("speed")),
                "wind_deg": as_float(wind.get("deg")),
                "wind_gust": as_float(wind.get("gust")),
                "visibility": as_float(record.get("visibility")),
                "pop": as_float(record.get("pop")),
                "rain_3h": as_float(_dict(record.get("rain")).get("3h")) or 0.0,
                "snow_3h": as_float(_dict(record.get("snow")).get("3h")) or 0.0,
                "part_of_day": _dict(record.get("sys")).get("pod"),
                **_weather_fields(record),
            }
        )
    return {
        **context,
        "issued_at": context["snapshot_at"],
        "city_population": as_int(city.get("population")),
        "sunrise": from_unix(city.get("sunrise")),
        "sunset": from_unix(city.get("sunset")),
        "items": items,
    }


def extract_air_pollution_forecast(source_object: dict[str, Any]) -> dict[str, Any] | None:
    context = job_context(source_object, "air_pollution_forecast")
    if context is None:
        return None
    items = [
        {"forecast_time": from_unix(record.get("dt")), **_air_fields(record)}
        for record in source_object["response"].get("list") or []
        if isinstance(record, dict) and from_unix(record.get("dt")) is not None
    ]
    return {**context, "issued_at": context["snapshot_at"], "items": items}


EXTRACTORS = {
    "current_weather": extract_current_weather,
    "air_pollution": extract_air_pollution,
    "forecast_5d_3h": extract_forecast,
    "air_pollution_forecast": extract_air_pollution_forecast,
}


def observation_hour(sample: dict[str, Any]) -> datetime:
    snapshot: datetime = sample["snapshot_at"]
    return snapshot.replace(minute=0, second=0, microsecond=0)
