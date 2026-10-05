from datetime import UTC, datetime

from botocore.exceptions import ClientError

from shared.storage import (
    build_raw_hour_prefix,
    build_source_key,
    put_json_once,
    sanitize_component,
    state_from_key,
)


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


def test_state_from_key() -> None:
    assert state_from_key("raw/x/state=sp/city=sao-paulo/file.json") == "SP"
    assert state_from_key("raw/x/openweather_current_weather_20260625T1200Z_ab12cd34.json") is None


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
