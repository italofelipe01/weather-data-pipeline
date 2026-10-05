import io
from datetime import UTC, date, datetime, timedelta

import pyarrow.parquet as pq

from shared.daily_table import (
    DAILY_SCHEMA,
    aggregate_daily,
    build_curated_daily_key,
    daily_records_to_parquet,
    local_day_is_closed,
    utc_hours_for_local_date,
)


def _hourly(state: str, hour: datetime, local_date: date, temp: float, rain: float = 0.0, aqi: int | None = 2, icon: str = "01d") -> dict:
    return {
        "observation_timestamp": hour,
        "local_date": local_date,
        "state": state,
        "city": "Cidade",
        "region": "Sudeste",
        "temperature_avg": temp,
        "temperature_min": temp - 1,
        "temperature_max": temp + 1,
        "humidity_avg": 60.0,
        "humidity_min": 50.0,
        "humidity_max": 70.0,
        "rain_mm": rain,
        "aqi": aqi,
        "pm2_5": 10.0,
        "weather_main": "Clear" if icon.startswith("01") else "Rain",
        "weather_icon": icon,
        "sunrise": hour.replace(hour=9),
        "sunset": hour.replace(hour=21),
        "sample_count": 20,
    }


def test_daily_key_and_hour_window() -> None:
    assert build_curated_daily_key(date(2026, 6, 25)) == "curated/daily_observations/year=2026/month=06/day=25/weather_daily_observations_20260625.parquet"
    hours = utc_hours_for_local_date(date(2026, 6, 25))
    assert hours[0] == datetime(2026, 6, 25, 3, tzinfo=UTC)
    assert hours[-1] == datetime(2026, 6, 26, 4, tzinfo=UTC)
    assert len(hours) == 26


def test_local_day_is_closed_after_westernmost_capital_finishes() -> None:
    assert local_day_is_closed(date(2026, 6, 25), datetime(2026, 6, 26, 4, 59, tzinfo=UTC)) is False
    assert local_day_is_closed(date(2026, 6, 25), datetime(2026, 6, 26, 5, 0, tzinfo=UTC)) is True


def test_aggregate_daily_by_local_date() -> None:
    start = datetime(2026, 6, 25, 3, tzinfo=UTC)
    rows = [_hourly("SP", start + timedelta(hours=index), date(2026, 6, 25), 15.0 + index, rain=1.0 if index in (5, 6) else 0.0) for index in range(24)]
    rows.append(_hourly("SP", start - timedelta(hours=1), date(2026, 6, 24), 99.0))
    rows.append(_hourly("SP", start + timedelta(hours=2), date(2026, 6, 25), 20.0, icon="10n", aqi=None))
    records = aggregate_daily(rows, date(2026, 6, 25), processed_at=datetime(2026, 6, 26, 6, tzinfo=UTC))
    assert len(records) == 1
    record = records[0]
    assert record["temperature_min"] == 14.0
    assert record["temperature_max"] == 39.0
    assert record["temperature_amplitude"] == 25.0
    assert record["rain_mm"] == 2.0
    assert record["rain_hours"] == 2
    assert record["hours_observed"] == 25
    assert record["weather_main"] == "Clear"
    assert record["aqi_max"] == 2
    assert record["sample_count"] == 500

    table = pq.read_table(io.BytesIO(daily_records_to_parquet(records)))
    assert table.schema.equals(DAILY_SCHEMA)
