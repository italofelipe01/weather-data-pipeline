import io
import json
import urllib.error

import pytest

from shared import openweather
from shared.openweather import (
    AIR_POLLUTION_FORECAST_URL,
    AIR_POLLUTION_URL,
    CURRENT_WEATHER_URL,
    FORECAST_5D_3H_URL,
    PRODUCTS,
    SourceError,
    build_free_plan_url,
    fetch_free_plan_weather,
    redact_api_key,
    validate_free_plan_response,
)

JOB = {"product": "current_weather", "latitude": -23.55, "longitude": -46.63, "units": "metric", "lang": "pt_br"}


def test_build_free_plan_url_uses_current_weather_endpoint() -> None:
    url = build_free_plan_url(JOB, "secret-key")
    assert url.startswith(f"{CURRENT_WEATHER_URL}?")
    assert "appid=secret-key" in url
    assert "units=metric" in url
    assert "lang=pt_br" in url


def test_build_free_plan_url_uses_forecast_endpoint() -> None:
    url = build_free_plan_url({"product": "forecast_5d_3h", "latitude": -23.55, "longitude": -46.63}, "secret-key")
    assert url.startswith(f"{FORECAST_5D_3H_URL}?")


def test_air_pollution_urls_skip_weather_only_parameters() -> None:
    current = build_free_plan_url({**JOB, "product": "air_pollution"}, "k")
    forecast = build_free_plan_url({**JOB, "product": "air_pollution_forecast"}, "k")
    assert current.startswith(f"{AIR_POLLUTION_URL}?")
    assert forecast.startswith(f"{AIR_POLLUTION_FORECAST_URL}?")
    assert "units=" not in current and "lang=" not in forecast


def test_unknown_product_is_not_retryable() -> None:
    with pytest.raises(SourceError) as error:
        build_free_plan_url({**JOB, "product": "one_call_3"}, "k")
    assert error.value.retryable is False


def test_every_product_is_free_plan() -> None:
    assert set(PRODUCTS) == {"current_weather", "forecast_5d_3h", "air_pollution", "air_pollution_forecast"}


def test_redact_api_key() -> None:
    assert "secret" not in redact_api_key("https://x.test/path?lat=1&appid=secret&cnt=10")
    assert "appid=%2A%2A%2A" in redact_api_key("https://x.test/path?lat=1&appid=secret&cnt=10")


def test_validate_free_plan_response_accepts_valid_payloads() -> None:
    validate_free_plan_response("current_weather", {"dt": 1704067200, "main": {"temp": 30.1}})
    validate_free_plan_response("forecast_5d_3h", {"list": [{"dt": 1704067200, "main": {"temp": 30.1}}]})
    air = {"list": [{"dt": 1704067200, "main": {"aqi": 2}, "components": {"pm2_5": 3.0}}]}
    validate_free_plan_response("air_pollution", air)
    validate_free_plan_response("air_pollution_forecast", air)


@pytest.mark.parametrize(
    ("product", "payload", "message"),
    [
        ("forecast_5d_3h", {"list": []}, "non-empty"),
        ("current_weather", {"main": {}}, "dt and main"),
        ("forecast_5d_3h", {"list": [{"temp": 10}]}, "integer dt"),
        ("air_pollution", {"list": []}, "non-empty"),
        ("air_pollution", {"list": [{"main": {"aqi": 1}}]}, "integer dt"),
        ("air_pollution", {"list": [{"dt": 1, "main": {}}]}, "main.aqi"),
        ("current_weather", [], "JSON object"),
        ("unknown", {}, "unsupported"),
    ],
)
def test_validate_free_plan_response_rejects_invalid_payloads(product, payload, message) -> None:
    with pytest.raises(SourceError, match=message) as error:
        validate_free_plan_response(product, payload)
    assert error.value.retryable is False


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_returns_validated_payload(monkeypatch) -> None:
    body = json.dumps({"dt": 1, "main": {"temp": 20}}).encode("utf-8")
    monkeypatch.setattr(openweather.urllib.request, "urlopen", lambda request, timeout: _Response(body))
    assert fetch_free_plan_weather(JOB, "key")["main"]["temp"] == 20


@pytest.mark.parametrize(("code", "retryable"), [(401, True), (404, False), (429, True), (503, True), (400, False)])
def test_fetch_classifies_http_errors(monkeypatch, code, retryable) -> None:
    def fail(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "error", {}, None)

    monkeypatch.setattr(openweather.urllib.request, "urlopen", fail)
    with pytest.raises(SourceError) as error:
        fetch_free_plan_weather(JOB, "super-secret")
    assert error.value.retryable is retryable
    assert error.value.status_code == code
    assert "super-secret" not in str(error.value)
    assert error.value.__cause__ is None


def test_fetch_retries_network_errors_and_invalid_json(monkeypatch) -> None:
    def offline(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(openweather.urllib.request, "urlopen", offline)
    with pytest.raises(SourceError) as error:
        fetch_free_plan_weather(JOB, "key")
    assert error.value.retryable is True

    monkeypatch.setattr(openweather.urllib.request, "urlopen", lambda request, timeout: _Response(b"<html>"))
    with pytest.raises(SourceError, match="invalid JSON"):
        fetch_free_plan_weather(JOB, "key")
