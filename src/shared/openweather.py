from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_5D_3H_URL = "https://api.openweathermap.org/data/2.5/forecast"


class SourceError(RuntimeError):
    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def build_free_plan_url(job: dict[str, Any], api_key: str) -> str:
    product = str(job["product"])
    if product == "current_weather":
        base_url = CURRENT_WEATHER_URL
    elif product == "forecast_5d_3h":
        base_url = FORECAST_5D_3H_URL
    else:
        raise SourceError(f"unsupported product: {product}", retryable=False)
    params = {
        "lat": str(job["latitude"]),
        "lon": str(job["longitude"]),
        "appid": api_key,
        "units": str(job.get("units") or "metric"),
        "lang": str(job.get("lang") or "pt_br"),
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def redact_api_key(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [(key, "***" if key == "appid" else value) for key, value in pairs]
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(redacted)))


def fetch_free_plan_weather(job: dict[str, Any], api_key: str, timeout_seconds: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        build_free_plan_url(job, api_key),
        headers={"User-Agent": "weather-data-pipeline/0.1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        retryable = exc.code in {408, 429, 500, 502, 503, 504}
        raise SourceError(f"openweather returned HTTP {exc.code}", retryable=retryable) from exc
    except urllib.error.URLError as exc:
        raise SourceError("openweather request failed", retryable=True) from exc

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceError("openweather returned invalid JSON", retryable=True) from exc

    validate_free_plan_response(str(job["product"]), payload)
    return payload


def validate_free_plan_response(product: str, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise SourceError("response must be a JSON object", retryable=False)
    if product == "current_weather":
        if not isinstance(payload.get("dt"), int) or not isinstance(payload.get("main"), dict):
            raise SourceError("current weather response must contain dt and main", retryable=False)
        return
    if product == "forecast_5d_3h":
        records = payload.get("list")
        if not isinstance(records, list) or not records:
            raise SourceError("forecast response.list must be a non-empty list", retryable=False)
        if not all(isinstance(record, dict) and isinstance(record.get("dt"), int) for record in records):
            raise SourceError("each forecast record must contain integer dt", retryable=False)
        return
    raise SourceError(f"unsupported product: {product}", retryable=False)
