import io
from datetime import UTC, date, datetime

import pyarrow.parquet as pq

from shared.hourly_table import (
    HOURLY_SCHEMA,
    aggregate_hourly,
    build_curated_hourly_key,
    build_raw_hour_prefix,
    normalize_hourly_record,
    parse_target_hour,
    records_to_parquet,
)
from shared.observations import extract_air_pollution, extract_current_weather
from shared.parquet_io import parquet_to_records
from tests.helpers import air_pollution_response, current_weather_response, source_object

PROCESSED_AT = datetime(2026, 6, 25, 13, tzinfo=UTC)


def _weather(snapshot: str, observed: str, temp: float, rain: float | None = None, state: str = "SP") -> dict:
    return extract_current_weather(source_object(state, "current_weather", snapshot, current_weather_response(observed, temp, rain)))


def test_build_hour_prefixes() -> None:
    target = datetime(2026, 6, 25, 12, tzinfo=UTC)
    assert build_raw_hour_prefix(target) == "raw/source=openweather-free-plan/product=current_weather/year=2026/month=06/day=25/hour=12/"
    assert build_curated_hourly_key(target) == (
        "curated/hourly_observations/year=2026/month=06/day=25/hour=12/weather_hourly_observations_20260625T1200Z.parquet"
    )


def test_parse_target_hour() -> None:
    assert parse_target_hour("2026-06-25T12:59:59Z") == datetime(2026, 6, 25, 12, tzinfo=UTC)
    assert parse_target_hour(None, now=datetime(2026, 6, 25, 13, 20, tzinfo=UTC)) == datetime(2026, 6, 25, 12, tzinfo=UTC)


def test_repeated_observations_count_once() -> None:
    # Snapshots every 3 minutes, but OpenWeather only refreshed the observation twice.
    samples = [
        _weather("2026-06-25T12:00:00Z", "2026-06-25T11:58:00Z", 20.0),
        _weather("2026-06-25T12:03:00Z", "2026-06-25T11:58:00Z", 20.0),
        _weather("2026-06-25T12:06:00Z", "2026-06-25T11:58:00Z", 20.0),
        _weather("2026-06-25T12:09:00Z", "2026-06-25T12:08:00Z", 26.0),
    ]
    record = aggregate_hourly(samples, processed_at=PROCESSED_AT)[0]
    assert record["temperature_avg"] == 23.0
    assert record["temperature_min"] == 20.0
    assert record["temperature_max"] == 26.0
    assert record["sample_count"] == 4
    assert record["observation_count"] == 2


def test_rain_is_mean_intensity_not_sum_of_snapshots() -> None:
    # rain.1h is mm/h; summing 20 snapshots per hour would report ~20x the real rainfall.
    samples = [
        _weather(f"2026-06-25T12:{minute:02d}:00Z", f"2026-06-25T12:{minute:02d}:00Z", 22.0, rain)
        for minute, rain in [(0, 2.0), (10, 2.0), (20, None), (30, 4.0)]
    ]
    record = aggregate_hourly(samples, processed_at=PROCESSED_AT)[0]
    assert record["rain_mm"] == 2.0
    assert record["rain_rate_max"] == 4.0


def test_weather_and_air_quality_are_merged_per_capital_hour() -> None:
    weather = [_weather("2026-06-25T12:10:00Z", "2026-06-25T12:05:00Z", 22.0)]
    air = [extract_air_pollution(source_object("SP", "air_pollution", "2026-06-25T12:35:00Z", air_pollution_response("2026-06-25T12:00:00Z", 3, 30.0)))]
    only_air = [extract_air_pollution(source_object("RJ", "air_pollution", "2026-06-25T12:35:00Z"))]
    records = aggregate_hourly(weather, air + only_air, processed_at=PROCESSED_AT)
    by_state = {record["state"]: record for record in records}
    assert by_state["SP"]["aqi"] == 3
    assert by_state["SP"]["pm2_5"] == 30.0
    assert by_state["SP"]["air_sample_count"] == 1
    assert by_state["SP"]["weather_main"] == "Clouds"
    assert by_state["RJ"]["temperature_avg"] is None
    assert by_state["RJ"]["sample_count"] == 0


def test_local_date_uses_capital_offset() -> None:
    record = aggregate_hourly([_weather("2026-06-26T02:10:00Z", "2026-06-26T02:05:00Z", 18.0, state="AC")], processed_at=PROCESSED_AT)[0]
    assert record["observation_date"] == date(2026, 6, 26)
    assert record["local_date"] == date(2026, 6, 25)
    assert record["local_hour"] == 21
    assert record["region"] == "Norte"


def test_records_to_parquet_round_trip() -> None:
    weather = [_weather("2026-06-25T12:10:00Z", "2026-06-25T12:05:00Z", 22.0)]
    parquet_body = records_to_parquet(aggregate_hourly(weather, processed_at=PROCESSED_AT))
    table = pq.read_table(io.BytesIO(parquet_body))
    assert table.schema.equals(HOURLY_SCHEMA)
    assert str(table.schema.field("observation_date").type) == "date32[day]"
    rows = parquet_to_records(parquet_body)
    assert rows[0]["observation_date"] == date(2026, 6, 25)
    assert rows[0]["observation_timestamp"] == datetime(2026, 6, 25, 12, tzinfo=UTC)
    assert rows[0]["processed_at"] == PROCESSED_AT
    assert rows[0]["city"] == "Sao Paulo"
    assert rows[0]["temperature_avg"] == 22.0


def test_normalize_legacy_rows() -> None:
    legacy = {
        "state": "SP",
        "observation_timestamp": datetime(2026, 6, 25, 2, tzinfo=UTC),
        "rain_1h_sum": 20.0,
        "sample_count": 20,
    }
    row = normalize_hourly_record(legacy)
    assert row["local_date"] == date(2026, 6, 24)
    assert row["local_hour"] == 23
    assert row["rain_mm"] == 1.0
    assert row["region"] == "Sudeste"
