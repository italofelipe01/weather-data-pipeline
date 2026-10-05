from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError

from shared.capitals import capital_by_state
from shared.storage import build_source_key, build_source_object


def _client_error(code: str, status: int, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, operation)


class MemoryS3:
    """In-memory stand-in for the subset of the S3 client API used by the pipeline."""

    def __init__(self, page_size: int = 1000) -> None:
        self.buckets: dict[str, dict[str, dict[str, Any]]] = {}
        self.page_size = page_size
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _bucket(self, name: str) -> dict[str, dict[str, Any]]:
        return self.buckets.setdefault(name, {})

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("put_object", kwargs))
        bucket = self._bucket(kwargs["Bucket"])
        if kwargs.get("IfNoneMatch") == "*" and kwargs["Key"] in bucket:
            raise _client_error("PreconditionFailed", 412, "PutObject")
        body = kwargs["Body"]
        bucket[kwargs["Key"]] = {**kwargs, "Body": body if isinstance(body, bytes) else str(body).encode("utf-8")}
        return {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_object", kwargs))
        item = self._bucket(kwargs["Bucket"]).get(kwargs["Key"])
        if item is None:
            raise _client_error("NoSuchKey", 404, "GetObject")
        return {"Body": io.BytesIO(item["Body"])}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("head_object", kwargs))
        if kwargs["Key"] not in self._bucket(kwargs["Bucket"]):
            raise _client_error("404", 404, "HeadObject")
        return {}

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("list_objects_v2", kwargs))
        keys = sorted(key for key in self._bucket(kwargs["Bucket"]) if key.startswith(kwargs.get("Prefix", "")))
        start = int(kwargs.get("ContinuationToken") or 0)
        page = keys[start : start + self.page_size]
        truncated = start + self.page_size < len(keys)
        response: dict[str, Any] = {"Contents": [{"Key": key} for key in page], "IsTruncated": truncated}
        if truncated:
            response["NextContinuationToken"] = str(start + self.page_size)
        return response

    def body(self, bucket: str, key: str) -> bytes:
        return self.buckets[bucket][key]["Body"]

    def keys(self, bucket: str, prefix: str = "") -> list[str]:
        return sorted(key for key in self.buckets.get(bucket, {}) if key.startswith(prefix))

    def count(self, operation: str) -> int:
        return sum(1 for name, _ in self.calls if name == operation)


def job(state: str, product: str, snapshot_at: str) -> dict[str, Any]:
    capital = capital_by_state(state)
    assert capital is not None
    return {
        "source": "openweather-free-plan",
        "product": product,
        "city": capital["city"],
        "state": state,
        "ibge_code": capital["ibge_code"],
        "latitude": capital["latitude"],
        "longitude": capital["longitude"],
        "timezone": capital["timezone"],
        "snapshot_at": snapshot_at,
        "units": "metric",
        "lang": "pt_br",
    }


def _unix(value: str) -> int:
    return int(utc(value).timestamp())


def current_weather_response(observed_at: str, temp: float = 25.0, rain_1h: float | None = None, **overrides: Any) -> dict[str, Any]:
    response: dict[str, Any] = {
        "coord": {"lon": -46.63, "lat": -23.55},
        "weather": [{"id": 803, "main": "Clouds", "description": "nublado", "icon": "04d"}],
        "main": {
            "temp": temp,
            "feels_like": temp + 1,
            "temp_min": temp - 1,
            "temp_max": temp + 1,
            "pressure": 1012,
            "humidity": 70,
            "sea_level": 1012,
            "grnd_level": 925,
        },
        "visibility": 10000,
        "wind": {"speed": 3.2, "deg": 120, "gust": 6.1},
        "clouds": {"all": 75},
        "dt": _unix(observed_at),
        "sys": {"country": "BR", "sunrise": _unix(observed_at) - 6 * 3600, "sunset": _unix(observed_at) + 5 * 3600},
        "timezone": -10800,
        "name": "Sao Paulo",
        "cod": 200,
    }
    if rain_1h is not None:
        response["rain"] = {"1h": rain_1h}
    response.update(overrides)
    return response


def air_pollution_response(observed_at: str, aqi: int = 2, pm2_5: float = 12.5) -> dict[str, Any]:
    return {
        "coord": {"lon": -46.63, "lat": -23.55},
        "list": [
            {
                "dt": _unix(observed_at),
                "main": {"aqi": aqi},
                "components": {"co": 230.3, "no": 0.1, "no2": 9.8, "o3": 40.1, "so2": 2.2, "pm2_5": pm2_5, "pm10": 20.0, "nh3": 1.1},
            }
        ],
    }


def forecast_response(issued_at: str, count: int = 8, temp: float = 24.0) -> dict[str, Any]:
    issued = utc(issued_at).replace(minute=0, second=0)
    start = issued + timedelta(hours=3 - issued.hour % 3)
    items = []
    for index in range(count):
        moment = start + timedelta(hours=3 * index)
        items.append(
            {
                "dt": int(moment.timestamp()),
                "main": {"temp": temp + index, "feels_like": temp + index, "temp_min": temp - 1, "temp_max": temp + 1, "pressure": 1010, "humidity": 60},
                "weather": [{"id": 500, "main": "Rain", "description": "chuva leve", "icon": "10d"}],
                "clouds": {"all": 90},
                "wind": {"speed": 4.0, "deg": 200, "gust": 7.0},
                "visibility": 10000,
                "pop": 0.4,
                "rain": {"3h": 1.2},
                "sys": {"pod": "d"},
                "dt_txt": moment.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return {
        "cod": "200",
        "cnt": count,
        "list": items,
        "city": {
            "name": "Sao Paulo",
            "population": 12_000_000,
            "timezone": -10800,
            "sunrise": int(start.timestamp()),
            "sunset": int(start.timestamp()) + 43000,
        },
    }


def air_pollution_forecast_response(issued_at: str, hours: int = 6) -> dict[str, Any]:
    start = utc(issued_at).replace(minute=0, second=0)
    return {
        "coord": {"lon": -46.63, "lat": -23.55},
        "list": [
            {
                "dt": int((start + timedelta(hours=index)).timestamp()),
                "main": {"aqi": 1 + index % 3},
                "components": {"co": 200.0, "no": 0.0, "no2": 5.0, "o3": 30.0 + index, "so2": 1.0, "pm2_5": 8.0, "pm10": 12.0, "nh3": 0.5},
            }
            for index in range(hours)
        ],
    }


RESPONSE_BUILDERS = {
    "current_weather": current_weather_response,
    "air_pollution": air_pollution_response,
    "forecast_5d_3h": forecast_response,
    "air_pollution_forecast": air_pollution_forecast_response,
}


def source_object(state: str, product: str, snapshot_at: str, response: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = response if response is not None else RESPONSE_BUILDERS[product](snapshot_at)
    return build_source_object(job(state, product, snapshot_at), payload)


def store_raw(s3: MemoryS3, bucket: str, state: str, product: str, snapshot_at: str, response: dict[str, Any] | None = None) -> str:
    obj = source_object(state, product, snapshot_at, response)
    key = build_source_key(obj["job"])
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(obj).encode("utf-8"))
    return key


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
