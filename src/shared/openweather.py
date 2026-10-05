from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

API_BASE_URL = "https://api.openweathermap.org/data/2.5"
CURRENT_WEATHER_URL = f"{API_BASE_URL}/weather"
FORECAST_5D_3H_URL = f"{API_BASE_URL}/forecast"
AIR_POLLUTION_URL = f"{API_BASE_URL}/air_pollution"
AIR_POLLUTION_FORECAST_URL = f"{API_BASE_URL}/air_pollution/forecast"

RETRYABLE_HTTP_CODES = {401, 408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ProductSpec:
    name: str
    url: str
    weather_params: bool
    label: str


# Every product below is part of the OpenWeather Free plan (60 calls/minute, 1,000,000 calls/month).
PRODUCTS: dict[str, ProductSpec] = {
    "current_weather": ProductSpec("current_weather", CURRENT_WEATHER_URL, True, "Current Weather API"),
    "forecast_5d_3h": ProductSpec("forecast_5d_3h", FORECAST_5D_3H_URL, True, "5 Day / 3 Hour Forecast API"),
    "air_pollution": ProductSpec("air_pollution", AIR_POLLUTION_URL, False, "Air Pollution API (current)"),
    "air_pollution_forecast": ProductSpec("air_pollution_forecast", AIR_POLLUTION_FORECAST_URL, False, "Air Pollution API (4-day hourly forecast)"),
}


class SourceError(RuntimeError):
    def __init__(self, message: str, retryable: bool = True, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


def get_product(product: str) -> ProductSpec:
    spec = PRODUCTS.get(product)
    if spec is None:
        raise SourceError(f"unsupported product: {product}", retryable=False)
    return spec


def build_free_plan_url(job: dict[str, Any], api_key: str) -> str:
    spec = get_product(str(job["product"]))
    params = {
        "lat": str(job["latitude"]),
        "lon": str(job["longitude"]),
        "appid": api_key,
    }
    if spec.weather_params:
        params["units"] = str(job.get("units") or "metric")
        params["lang"] = str(job.get("lang") or "pt_br")
    return f"{spec.url}?{urllib.parse.urlencode(params)}"


def redact_api_key(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [(key, "***" if key == "appid" else value) for key, value in pairs]
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(redacted)))


def fetch_free_plan_weather(job: dict[str, Any], api_key: str, timeout_seconds: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        build_free_plan_url(job, api_key),
        headers={"User-Agent": "weather-data-pipeline/0.2", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        # 401 is retried because a rotated or freshly activated key is picked up on the next attempt.
        raise SourceError(f"openweather returned HTTP {exc.code}", retryable=exc.code in RETRYABLE_HTTP_CODES, status_code=exc.code) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SourceError(f"openweather request failed: {type(exc).__name__}", retryable=True) from None

    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceError("openweather returned invalid JSON", retryable=True) from exc

    validate_free_plan_response(str(job["product"]), payload)
    return payload


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_free_plan_response(product: str, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise SourceError("response must be a JSON object", retryable=False)
    if product == "current_weather":
        if not _is_int(payload.get("dt")) or not isinstance(payload.get("main"), dict):
            raise SourceError("current weather response must contain dt and main", retryable=False)
        return
    if product == "forecast_5d_3h":
        records = payload.get("list")
        if not isinstance(records, list) or not records:
            raise SourceError("forecast response.list must be a non-empty list", retryable=False)
        if not all(isinstance(record, dict) and _is_int(record.get("dt")) for record in records):
            raise SourceError("each forecast record must contain integer dt", retryable=False)
        return
    if product in {"air_pollution", "air_pollution_forecast"}:
        records = payload.get("list")
        if not isinstance(records, list) or not records:
            raise SourceError("air pollution response.list must be a non-empty list", retryable=False)
        for record in records:
            if not isinstance(record, dict) or not _is_int(record.get("dt")):
                raise SourceError("each air pollution record must contain integer dt", retryable=False)
            main = record.get("main")
            if not isinstance(main, dict) or not _is_int(main.get("aqi")) or not isinstance(record.get("components"), dict):
                raise SourceError("each air pollution record must contain main.aqi and components", retryable=False)
        return
    raise SourceError(f"unsupported product: {product}", retryable=False)
