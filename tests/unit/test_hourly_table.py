import io
from datetime import UTC, datetime

import pyarrow.parquet as pq

from shared.hourly_table import (
    aggregate_hourly,
    build_curated_hourly_key,
    build_raw_hour_prefix,
    extract_current_weather_sample,
    parse_target_hour,
    records_to_parquet,
)


def _source_object(temp: float, snapshot_at: str = "2026-06-25T12:10:00Z") -> dict:
    return {
        "job": {
            "product": "current_weather",
            "city": "Sao Paulo",
            "state": "SP",
            "ibge_code": "3550308",
            "latitude": -23.5505,
            "longitude": -46.6333,
            "snapshot_at": snapshot_at,
        },
        "response": {
            "dt": 1782390000,
            "main": {"temp": temp, "temp_min": temp - 1, "temp_max": temp + 1, "feels_like": temp + 0.5, "humidity": 70, "pressure": 1012},
            "wind": {"speed": 3.2},
            "clouds": {"all": 40},
            "rain": {"1h": 0.5},
        },
    }


def test_build_hour_prefixes() -> None:
    target = datetime(2026, 6, 25, 12, tzinfo=UTC)
    assert build_raw_hour_prefix(target) == "raw/source=openweather-free-plan/product=current_weather/year=2026/month=06/day=25/hour=12/"
    assert build_curated_hourly_key(target) == (
        "curated/hourly_observations/year=2026/month=06/day=25/hour=12/weather_hourly_observations_20260625T1200Z.parquet"
    )


def test_parse_target_hour_rounds_down() -> None:
    assert parse_target_hour("2026-06-25T12:59:59Z") == datetime(2026, 6, 25, 12, tzinfo=UTC)


def test_extract_current_weather_sample() -> None:
    sample = extract_current_weather_sample(_source_object(22.5))
    assert sample is not None
    assert sample["city"] == "Sao Paulo"
    assert sample["temperature"] == 22.5
    assert sample["rain_1h"] == 0.5


def test_aggregate_hourly_records() -> None:
    samples = [
        extract_current_weather_sample(_source_object(22.0, "2026-06-25T12:10:00Z")),
        extract_current_weather_sample(_source_object(24.0, "2026-06-25T12:40:00Z")),
    ]
    records = aggregate_hourly([sample for sample in samples if sample], processed_at="2026-06-25T13:00:00Z")
    assert len(records) == 1
    assert records[0]["observation_date"] == "2026-06-25"
    assert records[0]["observation_hour"] == 12
    assert records[0]["temperature_avg"] == 23.0
    assert records[0]["sample_count"] == 2
    assert records[0]["rain_1h_sum"] == 1.0


def test_records_to_parquet_has_typed_columns() -> None:
    records = aggregate_hourly([extract_current_weather_sample(_source_object(22.0))], processed_at="2026-06-25T13:00:00Z")
    parquet_body = records_to_parquet(records)
    table = pq.read_table(io.BytesIO(parquet_body))
    assert str(table.schema.field("observation_date").type) == "date32[day]"
    assert str(table.schema.field("temperature_avg").type) == "double"
    rows = table.to_pylist()
    assert rows[0]["observation_date"].isoformat() == "2026-06-25"
    assert rows[0]["city"] == "Sao Paulo"
    assert rows[0]["temperature_avg"] == 22.0
