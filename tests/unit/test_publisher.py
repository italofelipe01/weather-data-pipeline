import json
from datetime import UTC, datetime

import pytest

from publisher import handler
from publisher.handler import PublisherConfig
from shared.call_budget import FileCallCounter
from tests.helpers import MemoryS3, current_weather_response, store_batch, store_raw

RAW = "raw-bucket"
SITE = "site-bucket"
CONFIG = PublisherConfig(raw_bucket=RAW, site_bucket=SITE, lookback_hours=2)


class FakeSsm:
    def get_parameter(self, **kwargs):
        return {"Parameter": {"Value": '{"month":"2026-06","calls":12345}'}}


def test_publish_latest_uses_newest_snapshot_per_capital(tmp_path) -> None:
    s3 = MemoryS3()
    store_raw(s3, RAW, "SP", "current_weather", "2026-06-25T12:51:00Z", current_weather_response("2026-06-25T12:50:00Z", 18.0))
    store_batch(s3, RAW, "current_weather", "2026-06-25T12:57:00Z", ("SP",), {"SP": current_weather_response("2026-06-25T12:55:00Z", 19.0)})
    store_raw(s3, RAW, "RJ", "current_weather", "2026-06-25T11:03:00Z", current_weather_response("2026-06-25T11:00:00Z", 27.0))
    store_batch(s3, RAW, "air_pollution", "2026-06-25T12:35:00Z", ("SP",))
    counter = FileCallCounter(tmp_path / "calls.json")
    counter.add(datetime(2026, 6, 25, tzinfo=UTC), 12_345)

    result = handler.publish_latest(s3, CONFIG, datetime(2026, 6, 25, 13, 2, tzinfo=UTC), counter)
    assert result["current_capitals"] == 2
    assert result["air_capitals"] == 1
    assert result["budget"]["calls_month_to_date"] == 12_345

    payload = json.loads(s3.body(SITE, "data/latest.json"))
    by_state = {item["state"]: item for item in payload["capitals"]}
    assert by_state["SP"]["current"]["temperature"] == 19.0
    assert by_state["RJ"]["current"]["temperature"] == 27.0
    assert by_state["SP"]["air"]["aqi"] == 2
    assert payload["latest_observation_at"] == "2026-06-25T12:55:00Z"
    assert payload["products"] == ["current_weather", "air_pollution"]
    assert s3.buckets[SITE]["data/latest.json"]["CacheControl"] == "public, max-age=60"
    assert payload["runtime"] == "aws"

    # A later run without new RJ data keeps the last known RJ values.
    store_raw(s3, RAW, "SP", "current_weather", "2026-06-25T15:00:00Z", current_weather_response("2026-06-25T15:00:00Z", 21.0))
    handler.publish_latest(s3, CONFIG, datetime(2026, 6, 25, 15, 5, tzinfo=UTC))
    payload = json.loads(s3.body(SITE, "data/latest.json"))
    by_state = {item["state"]: item for item in payload["capitals"]}
    assert by_state["SP"]["current"]["temperature"] == 21.0
    assert by_state["RJ"]["current"]["temperature"] == 27.0
    assert payload["budget"] is None


def test_lambda_handler(monkeypatch) -> None:
    s3 = MemoryS3()
    monkeypatch.setenv("RAW_DATA_BUCKET_NAME", RAW)
    monkeypatch.setenv("SITE_BUCKET_NAME", SITE)
    monkeypatch.setattr(handler, "_get_s3_client", lambda: s3)
    monkeypatch.setenv("CALL_COUNTER_PARAMETER_NAME", "/stack/openweather-call-counter")
    monkeypatch.setattr(handler, "_get_ssm_client", lambda: FakeSsm())
    result = handler.lambda_handler({}, None)
    assert result["current_capitals"] == 0
    assert "data/latest.json" in s3.keys(SITE)
    monkeypatch.delenv("SITE_BUCKET_NAME")
    with pytest.raises(RuntimeError, match="SITE_BUCKET_NAME"):
        handler.lambda_handler({}, None)
