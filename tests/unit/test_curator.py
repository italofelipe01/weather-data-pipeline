import json
from datetime import UTC, date, datetime, timedelta

import pytest

from curator import handler
from curator.handler import CuratorConfig
from shared.daily_table import build_curated_daily_key
from shared.forecast_table import build_curated_forecast_key
from shared.hourly_table import build_curated_hourly_key
from shared.parquet_io import parquet_to_records
from tests.helpers import MemoryS3, air_pollution_response, current_weather_response, store_raw

RAW = "raw-bucket"
SITE = "site-bucket"
CONFIG = CuratorConfig(raw_bucket=RAW, site_bucket=SITE, lookback_hours=3, daily_lookback_days=2, max_workers=4)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed_hour(s3: MemoryS3, hour: datetime, states: tuple[str, ...] = ("SP", "RJ"), temp: float = 20.0) -> None:
    for state in states:
        for minute in (0, 20, 40):
            moment = hour + timedelta(minutes=minute)
            store_raw(s3, RAW, state, "current_weather", _iso(moment), current_weather_response(_iso(moment), temp + minute / 20))
        air_moment = hour + timedelta(minutes=35)
        store_raw(s3, RAW, state, "air_pollution", _iso(air_moment), air_pollution_response(_iso(hour)))
        store_raw(s3, RAW, state, "forecast_5d_3h", _iso(hour + timedelta(minutes=5)))
    store_raw(s3, RAW, states[0], "air_pollution_forecast", _iso(hour + timedelta(minutes=50)))


def test_curate_hour_writes_hourly_and_forecast_tables() -> None:
    s3 = MemoryS3()
    hour = datetime(2026, 6, 25, 12, tzinfo=UTC)
    _seed_hour(s3, hour)
    result = handler.curate_hour(s3, CONFIG, hour)
    assert result["hourly"] == "written"
    assert result["forecast"] == "written"
    assert result["records"] == 2
    assert result["samples"] == 6
    rows = parquet_to_records(s3.body(RAW, build_curated_hourly_key(hour)))
    sp = next(row for row in rows if row["state"] == "SP")
    assert sp["temperature_avg"] == 21.0
    assert sp["aqi"] == 2
    assert s3.buckets[RAW][build_curated_hourly_key(hour)]["ContentType"] == "application/vnd.apache.parquet"
    forecast_rows = parquet_to_records(s3.body(RAW, build_curated_forecast_key(hour)))
    assert len(forecast_rows) == 16

    again = handler.curate_hour(s3, CONFIG, hour)
    assert again["hourly"] == "skipped_existing"
    assert again["forecast"] == "skipped_existing"


def test_curate_hour_without_raw_data_writes_nothing() -> None:
    s3 = MemoryS3()
    result = handler.curate_hour(s3, CONFIG, datetime(2026, 6, 25, 12, tzinfo=UTC))
    assert result["hourly"] == "no_data"
    assert result["forecast"] == "no_data"
    assert s3.keys(RAW, "curated/") == []


def test_scheduled_run_catches_up_missing_hours_and_publishes_frontend_data() -> None:
    s3 = MemoryS3()
    now = datetime(2026, 6, 25, 13, 20, tzinfo=UTC)
    for hours_ago in (1, 2, 3):
        _seed_hour(s3, datetime(2026, 6, 25, 13, tzinfo=UTC) - timedelta(hours=hours_ago))
    result = handler.run({}, s3, CONFIG, now)
    assert result["hours_written"] == 3
    assert result["forecasts_written"] == 3
    assert result["published"] == {"hourly": 27, "daily": 27, "forecast": 2}

    hourly = json.loads(s3.body(SITE, "data/hourly/sp.json"))
    assert len(hourly["rows"]) == 3
    assert hourly["capital"]["name"] == "São Paulo"
    assert json.loads(s3.body(SITE, "data/hourly/mg.json"))["rows"] == []
    forecast = json.loads(s3.body(SITE, "data/forecast/sp.json"))
    assert forecast["weather"]["issued_at"] == "2026-06-25T12:05:00Z"
    assert forecast["air"]["issued_at"] == "2026-06-25T12:50:00Z"
    rj_forecast = json.loads(s3.body(SITE, "data/forecast/rj.json"))
    assert rj_forecast["air"] is None
    assert s3.buckets[SITE]["data/hourly/sp.json"]["CacheControl"] == "public, max-age=300"

    second = handler.run({}, s3, CONFIG, now)
    assert second["hours_written"] == 0
    assert second["published"]["daily"] == 0


def test_daily_aggregation_runs_once_the_local_day_closes() -> None:
    s3 = MemoryS3()
    local_day = date(2026, 6, 25)
    for offset in range(3, 30):
        _seed_hour(s3, datetime(2026, 6, 25, tzinfo=UTC) + timedelta(hours=offset), states=("SP", "AC"))
    config = CuratorConfig(raw_bucket=RAW, site_bucket=SITE, lookback_hours=27, daily_lookback_days=1, max_workers=4)
    result = handler.run({}, s3, config, datetime(2026, 6, 26, 6, 20, tzinfo=UTC))
    # AC (UTC-5) hours before 05:00 UTC belong to 2026-06-24, so that closed day is refreshed as well.
    assert [item["date"] for item in result["daily"]] == ["2026-06-24", "2026-06-25"]
    daily_rows = parquet_to_records(s3.body(RAW, build_curated_daily_key(local_day)))
    assert {row["state"]: row["hours_observed"] for row in daily_rows} == {"AC": 24, "SP": 24}
    daily_json = json.loads(s3.body(SITE, "data/daily/sp.json"))
    assert [row["observation_date"] for row in daily_json["rows"]] == ["2026-06-25"]


def test_daily_series_merges_incrementally_and_can_rebuild() -> None:
    s3 = MemoryS3()
    for day in (24, 25):
        for offset in range(3, 29):
            _seed_hour(s3, datetime(2026, 6, day, tzinfo=UTC) + timedelta(hours=offset), states=("SP",))
    config = CuratorConfig(raw_bucket=RAW, site_bucket=SITE, lookback_hours=60, daily_lookback_days=1, max_workers=4)
    handler.run({"publish": False}, s3, config, datetime(2026, 6, 26, 6, 20, tzinfo=UTC))
    assert s3.keys(SITE) == []
    result = handler.run({"rebuild_serving": True}, s3, config, datetime(2026, 6, 26, 7, 20, tzinfo=UTC))
    assert result["published"]["daily"] == 27
    rows = json.loads(s3.body(SITE, "data/daily/sp.json"))["rows"]
    assert [row["observation_date"] for row in rows] == ["2026-06-24", "2026-06-25"]


def test_manual_events_force_reprocessing() -> None:
    s3 = MemoryS3()
    hour = datetime(2026, 6, 25, 12, tzinfo=UTC)
    _seed_hour(s3, hour)
    now = datetime(2026, 6, 25, 15, tzinfo=UTC)
    assert handler.run({"target_hour": "2026-06-25T12:30:00Z", "publish": False}, s3, CONFIG, now)["hours_written"] == 1
    assert handler.run({"target_hour": "2026-06-25T12:00:00Z", "publish": False}, s3, CONFIG, now)["hours_written"] == 1
    ranged = handler.run({"start_hour": "2026-06-25T11:00:00Z", "end_hour": "2026-06-25T12:00:00Z", "publish": False}, s3, CONFIG, now)
    assert [item["target_hour"] for item in ranged["hours"]] == ["2026-06-25T11:00:00Z", "2026-06-25T12:00:00Z"]
    with pytest.raises(ValueError, match="before"):
        handler.run({"start_hour": "2026-06-25T12:00:00Z", "end_hour": "2026-06-25T11:00:00Z"}, s3, CONFIG, now)
    with pytest.raises(ValueError, match="chunks"):
        handler.run({"start_hour": "2026-01-01T00:00:00Z", "end_hour": "2026-06-25T11:00:00Z"}, s3, CONFIG, now)


def test_lambda_handler_reads_configuration(monkeypatch) -> None:
    s3 = MemoryS3()
    monkeypatch.setenv("RAW_DATA_BUCKET_NAME", RAW)
    monkeypatch.delenv("SITE_BUCKET_NAME", raising=False)
    monkeypatch.setenv("METRICS_DISABLED", "true")
    monkeypatch.setattr(handler, "_get_s3_client", lambda: s3)
    result = handler.lambda_handler({"target_hour": "2026-06-25T12:00:00Z"}, None)
    assert result["published"] == {}
    json.dumps(result)
    monkeypatch.delenv("RAW_DATA_BUCKET_NAME")
    with pytest.raises(RuntimeError, match="RAW_DATA_BUCKET_NAME"):
        handler.lambda_handler({}, None)
