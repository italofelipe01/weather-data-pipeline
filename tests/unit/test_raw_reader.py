from datetime import UTC, datetime

from shared.observations import extract_current_weather, extract_forecast
from shared.raw_reader import expand_raw_object, key_timestamp, latest_by_state, read_hour
from tests.helpers import MemoryS3, current_weather_response, store_batch, store_raw

RAW = "raw"


def test_expand_handles_batch_and_legacy_objects() -> None:
    legacy = {"job": {"state": "SP"}, "response": {"dt": 1}}
    assert expand_raw_object(legacy) == [legacy]
    batch = {"format": "batch-v1", "source": "s", "items": [{"job": {"state": "SP"}, "response": {"dt": 1}}, "junk"]}
    assert expand_raw_object(batch) == [{"source": "s", "job": {"state": "SP"}, "response": {"dt": 1}, "retrieved_at": None}]


def test_key_timestamp() -> None:
    assert key_timestamp("x/openweather_current_weather_20260625T1203Z_ab12cd34.json") == "20260625T1203Z"
    assert key_timestamp("x/state=sp/openweather_current_weather_sp_sao-paulo_20260625T1203Z.json") == "20260625T1203Z"
    assert key_timestamp("x/other.json") == ""


def test_read_hour_mixes_layouts() -> None:
    s3 = MemoryS3()
    store_raw(s3, RAW, "MG", "current_weather", "2026-06-25T12:00:00Z")
    store_batch(s3, RAW, "current_weather", "2026-06-25T12:03:00Z", ("SP", "RJ"))
    objects, samples = read_hour(s3, RAW, "current_weather", datetime(2026, 6, 25, 12, tzinfo=UTC), extract_current_weather)
    assert objects == 2
    assert sorted(sample["state"] for sample in samples) == ["MG", "RJ", "SP"]


def test_latest_by_state_prefers_newest_and_reads_little() -> None:
    s3 = MemoryS3()
    store_batch(s3, RAW, "current_weather", "2026-06-25T11:57:00Z", ("SP", "RJ"), {"SP": current_weather_response("2026-06-25T11:55:00Z", 10.0)})
    store_batch(s3, RAW, "current_weather", "2026-06-25T12:57:00Z", ("SP",), {"SP": current_weather_response("2026-06-25T12:55:00Z", 30.0)})
    store_raw(s3, RAW, "MG", "current_weather", "2026-06-25T12:30:00Z")
    store_raw(s3, RAW, "MG", "current_weather", "2026-06-25T12:10:00Z")
    found = latest_by_state(s3, RAW, "current_weather", datetime(2026, 6, 25, 13, 1, tzinfo=UTC), 3, extract_current_weather, expected_states=3)
    assert found["SP"]["temperature"] == 30.0
    assert found["RJ"]["snapshot_at"] == datetime(2026, 6, 25, 11, 57, tzinfo=UTC)
    assert found["MG"]["snapshot_at"] == datetime(2026, 6, 25, 12, 30, tzinfo=UTC)
    reads = [call[1]["Key"] for call in s3.calls if call[0] == "get_object"]
    assert not any("1210Z" in key for key in reads)


def test_latest_by_state_for_forecast() -> None:
    s3 = MemoryS3()
    store_batch(s3, RAW, "forecast_5d_3h", "2026-06-25T12:05:00Z", ("SP", "RJ"))
    found = latest_by_state(s3, RAW, "forecast_5d_3h", datetime(2026, 6, 25, 12, 30, tzinfo=UTC), 2, extract_forecast)
    assert set(found) == {"SP", "RJ"}
    assert len(found["SP"]["items"]) == 8
