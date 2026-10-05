from datetime import UTC, datetime, timedelta

from shared.capitals import get_capitals
from shared.collection import (
    BATCH_FORMAT,
    build_batch_job,
    build_batch_key,
    capital_jobs,
    collect_batch,
    is_expired,
)
from shared.openweather import SourceError


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds

    def clock(self) -> float:
        return self.now


def _job(states=("SP", "RJ", "MG"), product="current_weather", snapshot_at="2026-06-25T12:03:00Z"):
    return build_batch_job(product, get_capitals(list(states)), "metric", "pt_br", snapshot_at)


def test_batch_job_expands_to_per_capital_jobs() -> None:
    job = _job()
    assert job["format"] == BATCH_FORMAT
    jobs = capital_jobs(job)
    assert {item["state"] for item in jobs} == {"SP", "RJ", "MG"}
    assert all(item["product"] == "current_weather" and item["snapshot_at"] == "2026-06-25T12:03:00Z" for item in jobs)
    assert jobs[0]["latitude"] and jobs[0]["units"] == "metric"


def test_batch_key_is_deterministic_per_product_snapshot_and_states() -> None:
    key = build_batch_key("current_weather", "2026-06-25T12:03:00Z", ["SP", "RJ"])
    assert key.startswith(
        "raw/source=openweather-free-plan/product=current_weather/year=2026/month=06/day=25/hour=12/openweather_current_weather_20260625T1203Z_"
    )
    assert key == build_batch_key("current_weather", "2026-06-25T12:03:40Z", ["rj", "sp"])
    assert key != build_batch_key("current_weather", "2026-06-25T12:03:00Z", ["SP"])


def test_collect_batch_paces_calls_and_retries_transient_errors() -> None:
    attempts: dict[str, int] = {}
    unauthorized: list[bool] = []

    def fetch(job):
        state = job["state"]
        attempts[state] = attempts.get(state, 0) + 1
        if state == "RJ" and attempts[state] == 1:
            raise SourceError("openweather returned HTTP 429", retryable=True, status_code=429)
        if state == "MG":
            raise SourceError("openweather returned HTTP 404", retryable=False, status_code=404)
        if state == "SP" and attempts[state] == 1:
            raise SourceError("openweather returned HTTP 401", retryable=True, status_code=401)
        return {"dt": 1, "main": {"temp": 20}}

    clock = FakeClock()
    result = collect_batch(_job(), fetch, min_interval=1.1, sleep=clock.sleep, clock=clock.clock, on_unauthorized=lambda: unauthorized.append(True))
    assert {item["job"]["state"] for item in result.items} == {"SP", "RJ"}
    assert [item["state"] for item in result.rejected] == ["MG"]
    assert result.failures == []
    assert result.calls == 5
    assert unauthorized == [True]
    assert all(value > 0 for value in clock.sleeps)
    raw = result.raw_object()
    assert raw["format"] == BATCH_FORMAT
    assert raw["failures"][0]["status_code"] == 404
    assert len(raw["items"][0]["response_hash"]) == 64


def test_collect_batch_gives_up_after_max_attempts_and_respects_time_budget() -> None:
    def always_down(job):
        raise SourceError("openweather returned HTTP 503", retryable=True, status_code=503)

    clock = FakeClock()
    result = collect_batch(_job(("SP",)), always_down, max_attempts=3, sleep=clock.sleep, clock=clock.clock)
    assert result.calls == 3
    assert result.failures[0]["status_code"] == 503
    assert clock.sleeps == [2.0, 5.0]

    skipped = collect_batch(_job(("SP", "RJ")), always_down, remaining_seconds=lambda: 5.0)
    assert skipped.calls == 0
    assert [item["error"] for item in skipped.failures] == ["time budget exhausted", "time budget exhausted"]


def test_old_snapshots_expire_per_product() -> None:
    snapshot = datetime(2026, 6, 25, 12, tzinfo=UTC)
    current = _job(snapshot_at="2026-06-25T12:00:00Z")
    forecast = _job(product="forecast_5d_3h", snapshot_at="2026-06-25T12:00:00Z")
    assert is_expired(current, snapshot + timedelta(minutes=14)) is False
    assert is_expired(current, snapshot + timedelta(minutes=16)) is True
    assert is_expired(forecast, snapshot + timedelta(minutes=60)) is False
