import json
from datetime import UTC, date, datetime

from shared.capitals import capital_by_state
from shared.observations import extract_air_pollution, extract_current_weather, extract_forecast
from shared.serving import (
    build_daily_payload,
    build_forecast_payload,
    build_hourly_payload,
    build_latest_payload,
    daily_key,
    forecast_key,
    hourly_key,
    json_value,
    merge_daily_rows,
)
from tests.helpers import source_object

NOW = datetime(2026, 6, 25, 13, 0, tzinfo=UTC)


def test_keys_are_lowercase_per_state() -> None:
    assert hourly_key("SP") == "data/hourly/sp.json"
    assert daily_key("RJ") == "data/daily/rj.json"
    assert forecast_key("AC") == "data/forecast/ac.json"


def test_json_value_serializes_dates_and_drops_nan() -> None:
    assert json_value({"a": [date(2026, 6, 25), datetime(2026, 6, 25, 12, tzinfo=UTC), float("nan"), 1.123456]}) == {
        "a": ["2026-06-25", "2026-06-25T12:00:00Z", None, 1.1235]
    }


def test_latest_payload_lists_all_capitals_and_keeps_previous_values() -> None:
    current = extract_current_weather(source_object("SP", "current_weather", "2026-06-25T12:57:00Z"))
    air = extract_air_pollution(source_object("SP", "air_pollution", "2026-06-25T12:35:00Z"))
    previous = {"capitals": [{"state": "RJ", "current": {"temperature": 30.0, "observed_at": "2026-06-25T10:00:00Z"}, "air": None}]}
    budget = {"calls_month_to_date": 1}
    payload = build_latest_payload({"SP": current}, {"SP": air}, NOW, budget=budget, previous=previous, products=["current_weather"])
    by_state = {item["state"]: item for item in payload["capitals"]}
    assert len(by_state) == 27
    assert by_state["SP"]["name"] == "São Paulo"
    assert by_state["SP"]["current"]["temperature"] == 25.0
    assert by_state["SP"]["air"]["aqi"] == 2
    assert by_state["RJ"]["current"]["temperature"] == 30.0
    assert by_state["MG"]["current"] is None
    assert payload["latest_observation_at"] == "2026-06-25T12:57:00Z"
    json.dumps(payload, allow_nan=False)


def test_series_payloads() -> None:
    capital = capital_by_state("SP")
    records = [
        {"observation_timestamp": datetime(2026, 6, 25, 12, tzinfo=UTC), "temperature_avg": 20.0},
        {"observation_timestamp": datetime(2026, 6, 25, 11, tzinfo=UTC)},
    ]
    hourly = build_hourly_payload(capital, records, NOW, 7)
    assert [row["observation_timestamp"] for row in hourly["rows"]] == ["2026-06-25T11:00:00Z", "2026-06-25T12:00:00Z"]
    merged = merge_daily_rows(
        [{"observation_date": "2026-06-23", "rain_mm": 1}, {"observation_date": "2026-06-24", "rain_mm": 1}],
        [{"observation_date": "2026-06-24", "rain_mm": 5}, {"observation_date": "2026-06-25", "rain_mm": 0}],
        max_days=2,
    )
    assert merged == [{"observation_date": "2026-06-24", "rain_mm": 5}, {"observation_date": "2026-06-25", "rain_mm": 0}]
    daily = build_daily_payload(capital, merged, NOW, 2)
    assert daily["capital"]["state"] == "SP"


def test_forecast_payload_handles_missing_parts() -> None:
    capital = capital_by_state("SP")
    forecast = extract_forecast(source_object("SP", "forecast_5d_3h", "2026-06-25T12:05:00Z"))
    payload = build_forecast_payload(capital, forecast, None, NOW)
    assert payload["weather"]["issued_at"] == "2026-06-25T12:05:00Z"
    assert len(payload["weather"]["items"]) == 8
    assert payload["air"] is None
    json.dumps(payload, allow_nan=False)
