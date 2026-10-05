from datetime import UTC, datetime

from shared.observations import (
    as_float,
    as_int,
    extract_air_pollution,
    extract_air_pollution_forecast,
    extract_current_weather,
    extract_forecast,
    observation_hour,
)
from tests.helpers import current_weather_response, source_object


def test_extract_current_weather_reads_every_documented_field() -> None:
    response = current_weather_response("2026-06-25T12:05:00Z", 22.5, 1.5)
    sample = extract_current_weather(source_object("SP", "current_weather", "2026-06-25T12:10:00Z", response))
    assert sample is not None
    assert sample["display_name"] == "São Paulo"
    assert sample["region"] == "Sudeste"
    assert sample["observed_at"] == datetime(2026, 6, 25, 12, 5, tzinfo=UTC)
    assert sample["snapshot_at"] == datetime(2026, 6, 25, 12, 10, tzinfo=UTC)
    assert sample["temperature"] == 22.5
    assert sample["rain_1h"] == 1.5
    assert sample["snow_1h"] == 0.0
    assert sample["wind_gust"] == 6.1
    assert sample["visibility"] == 10000
    assert sample["grnd_level"] == 925
    assert sample["weather_icon"] == "04d"
    assert sample["sunrise"] < sample["observed_at"] < sample["sunset"]
    assert observation_hour(sample) == datetime(2026, 6, 25, 12, tzinfo=UTC)


def test_extract_current_weather_ignores_other_products_and_bad_shapes() -> None:
    assert extract_current_weather(source_object("SP", "air_pollution", "2026-06-25T12:10:00Z")) is None
    assert extract_current_weather({"job": "x", "response": {}}) is None
    bare = source_object("SP", "current_weather", "2026-06-25T12:10:00Z", {"dt": "bad", "main": {"temp": "n/a"}, "weather": []})
    sample = extract_current_weather(bare)
    assert sample["temperature"] is None
    assert sample["observed_at"] == sample["snapshot_at"]
    assert sample["weather_main"] is None


def test_extract_air_pollution() -> None:
    sample = extract_air_pollution(source_object("RJ", "air_pollution", "2026-06-25T12:35:00Z"))
    assert sample["aqi"] == 2
    assert sample["pm2_5"] == 12.5
    assert sample["state"] == "RJ"
    assert extract_air_pollution(source_object("RJ", "air_pollution", "2026-06-25T12:35:00Z", {"list": []})) is None


def test_extract_forecasts() -> None:
    forecast = extract_forecast(source_object("SP", "forecast_5d_3h", "2026-06-25T12:05:00Z"))
    assert forecast["city_population"] == 12_000_000
    assert len(forecast["items"]) == 8
    assert forecast["items"][0]["pop"] == 0.4
    assert forecast["items"][0]["rain_3h"] == 1.2
    assert forecast["items"][0]["part_of_day"] == "d"
    air = extract_air_pollution_forecast(source_object("SP", "air_pollution_forecast", "2026-06-25T12:50:00Z"))
    assert [item["aqi"] for item in air["items"]] == [1, 2, 3, 1, 2, 3]


def test_number_coercion() -> None:
    assert as_float("1.5") == 1.5
    assert as_float(float("nan")) is None
    assert as_float(True) is None
    assert as_int("7.9") == 7
    assert as_int(None) is None
