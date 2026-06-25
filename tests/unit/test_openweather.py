from shared.openweather import (
    CURRENT_WEATHER_URL,
    FORECAST_5D_3H_URL,
    SourceError,
    build_free_plan_url,
    redact_api_key,
    validate_free_plan_response,
)


def test_build_free_plan_url_uses_current_weather_endpoint() -> None:
    url = build_free_plan_url(
        {
            "product": "current_weather",
            "latitude": -23.55,
            "longitude": -46.63,
            "units": "metric",
            "lang": "pt_br",
        },
        "secret-key",
    )
    assert url.startswith(f"{CURRENT_WEATHER_URL}?")
    assert "appid=secret-key" in url
    assert "units=metric" in url
    assert "lang=pt_br" in url


def test_build_free_plan_url_uses_forecast_endpoint() -> None:
    url = build_free_plan_url({"product": "forecast_5d_3h", "latitude": -23.55, "longitude": -46.63}, "secret-key")
    assert url.startswith(f"{FORECAST_5D_3H_URL}?")


def test_redact_api_key() -> None:
    assert "secret" not in redact_api_key("https://x.test/path?lat=1&appid=secret&cnt=10")
    assert "appid=%2A%2A%2A" in redact_api_key("https://x.test/path?lat=1&appid=secret&cnt=10")


def test_validate_free_plan_response_accepts_current_weather() -> None:
    validate_free_plan_response("current_weather", {"dt": 1704067200, "main": {"temp": 30.1}})


def test_validate_free_plan_response_accepts_forecast() -> None:
    validate_free_plan_response("forecast_5d_3h", {"list": [{"dt": 1704067200, "main": {"temp": 30.1}}]})


def test_validate_free_plan_response_rejects_empty_forecast_list() -> None:
    try:
        validate_free_plan_response("forecast_5d_3h", {"list": []})
    except SourceError as exc:
        assert exc.retryable is False
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("expected SourceError")


def test_validate_free_plan_response_rejects_missing_current_fields() -> None:
    try:
        validate_free_plan_response("current_weather", {"main": {}})
    except SourceError as exc:
        assert exc.retryable is False
        assert "dt and main" in str(exc)
    else:
        raise AssertionError("expected SourceError")


def test_validate_free_plan_response_rejects_missing_forecast_dt() -> None:
    try:
        validate_free_plan_response("forecast_5d_3h", {"list": [{"temp": 10}]})
    except SourceError as exc:
        assert exc.retryable is False
        assert "integer dt" in str(exc)
    else:
        raise AssertionError("expected SourceError")
