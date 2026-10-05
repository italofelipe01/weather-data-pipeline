from datetime import UTC, datetime

from botocore.exceptions import ClientError

from shared.storage import (
    build_raw_hour_prefix,
    build_source_key,
    find_latest_raw_keys,
    latest_keys_by_state,
    put_json_once,
    sanitize_component,
    state_from_key,
)
from tests.helpers import MemoryS3, store_raw


class FakeS3:
    def __init__(self, error: ClientError | None = None) -> None:
        self.error = error
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error


def test_sanitize_component() -> None:
    assert sanitize_component("São Paulo / SP") == "s-o-paulo-sp"
    assert sanitize_component("   ") == "unknown"


def test_build_source_key_is_deterministic() -> None:
    job = {"state": "SP", "city": "Sao Paulo", "product": "current_weather", "snapshot_at": "2026-06-25T12:00:00Z"}
    assert build_source_key(job) == (
        "raw/source=openweather-free-plan/product=current_weather/year=2026/month=06/day=25/hour=12/"
        "state=sp/city=sao-paulo/openweather_current_weather_sp_sao-paulo_20260625T1200Z.json"
    )


def test_build_raw_hour_prefix_for_air_pollution() -> None:
    assert build_raw_hour_prefix("air_pollution", datetime(2026, 6, 25, 12, 40, tzinfo=UTC)) == (
        "raw/source=openweather-free-plan/product=air_pollution/year=2026/month=06/day=25/hour=12/"
    )


def test_latest_keys_by_state_picks_newest_snapshot() -> None:
    keys = [
        "raw/x/state=sp/city=sao-paulo/openweather_current_weather_sp_sao-paulo_20260625T1203Z.json",
        "raw/x/state=sp/city=sao-paulo/openweather_current_weather_sp_sao-paulo_20260625T1257Z.json",
        "raw/x/state=rj/city=rio-de-janeiro/openweather_current_weather_rj_rio-de-janeiro_20260625T1200Z.json",
        "raw/x/no-state.json",
    ]
    latest = latest_keys_by_state(keys)
    assert latest["SP"].endswith("1257Z.json")
    assert set(latest) == {"SP", "RJ"}
    assert state_from_key("nothing") is None


def test_find_latest_raw_keys_looks_back_and_stops_early() -> None:
    s3 = MemoryS3()
    store_raw(s3, "raw", "SP", "current_weather", "2026-06-25T12:57:00Z")
    store_raw(s3, "raw", "RJ", "current_weather", "2026-06-25T11:30:00Z")
    now = datetime(2026, 6, 25, 13, 1, tzinfo=UTC)
    found = find_latest_raw_keys(s3, "raw", "current_weather", now, lookback_hours=3)
    assert set(found) == {"SP", "RJ"}
    assert s3.count("list_objects_v2") == 4

    s3.calls.clear()
    assert set(find_latest_raw_keys(s3, "raw", "current_weather", now, lookback_hours=3, expected_states=1)) == {"SP"}
    assert s3.count("list_objects_v2") == 2


def test_put_json_once_returns_duplicate_for_precondition_failed() -> None:
    error = ClientError(
        {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}},
        "PutObject",
    )
    assert put_json_once(FakeS3(error), "bucket", "key", {"ok": True}) == "duplicate"


def test_put_json_once_reraises_other_errors() -> None:
    error = ClientError({"Error": {"Code": "AccessDenied"}, "ResponseMetadata": {"HTTPStatusCode": 403}}, "PutObject")
    try:
        put_json_once(FakeS3(error), "bucket", "key", {"ok": True})
    except ClientError as exc:
        assert exc is error
    else:
        raise AssertionError("expected ClientError")


def test_put_json_once_uses_sse_and_if_none_match() -> None:
    fake = FakeS3()
    assert put_json_once(fake, "bucket", "key", {"ok": True}) == "stored"
    assert fake.calls[0]["ServerSideEncryption"] == "AES256"
    assert fake.calls[0]["IfNoneMatch"] == "*"
