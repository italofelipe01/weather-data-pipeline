import io
from datetime import UTC, datetime

import pyarrow.parquet as pq

from shared.forecast_table import FORECAST_SCHEMA, build_curated_forecast_key, build_forecast_records, forecast_records_to_parquet
from shared.observations import extract_forecast
from tests.helpers import forecast_response, source_object


def test_forecast_key() -> None:
    assert build_curated_forecast_key(datetime(2026, 6, 25, 12, 5, tzinfo=UTC)) == (
        "curated/forecast_3h/year=2026/month=06/day=25/hour=12/weather_forecast_3h_20260625T1200Z.parquet"
    )


def test_forecast_records_keep_latest_issue_per_capital() -> None:
    older = extract_forecast(source_object("SP", "forecast_5d_3h", "2026-06-25T12:05:00Z", forecast_response("2026-06-25T12:05:00Z", 4, temp=10.0)))
    newer = extract_forecast(source_object("SP", "forecast_5d_3h", "2026-06-25T12:45:00Z", forecast_response("2026-06-25T12:45:00Z", 4, temp=30.0)))
    records = build_forecast_records([older, newer], processed_at=datetime(2026, 6, 25, 13, tzinfo=UTC))
    assert len(records) == 4
    assert records[0]["temperature"] == 30.0
    assert records[0]["lead_hours"] == 2.25
    assert records[0]["local_forecast_hour"] == 12
    assert records[0]["rain_3h_mm"] == 1.2

    table = pq.read_table(io.BytesIO(forecast_records_to_parquet(records)))
    assert table.schema.equals(FORECAST_SCHEMA)
    assert table.num_rows == 4
