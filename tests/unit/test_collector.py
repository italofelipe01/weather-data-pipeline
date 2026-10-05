import json
from datetime import UTC, datetime, timedelta

import pytest

from collector import handler
from shared.capitals import get_capitals
from shared.collection import build_batch_job
from shared.openweather import SourceError
from tests.helpers import MemoryS3, current_weather_response


def _recent_job(states=("SP", "RJ"), product="current_weather", minutes_ago=1):
    snapshot = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).replace(second=0, microsecond=0)
    return build_batch_job(product, get_capitals(list(states)), "metric", "pt_br", snapshot.isoformat().replace("+00:00", "Z"))


class Context:
    aws_request_id = "req"

    def get_remaining_time_in_millis(self):
        return 280_000


@pytest.fixture
def s3(monkeypatch):
    fake = MemoryS3()
    monkeypatch.setenv("RAW_DATA_BUCKET_NAME", "bucket")
    monkeypatch.setenv("OPENWEATHER_API_KEY_PARAMETER_NAME", "/param")
    monkeypatch.setenv("SOURCE_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(handler, "_get_ssm_client", lambda: object())
    monkeypatch.setattr(handler, "get_openweather_api_key", lambda ssm_client, parameter_name: "secret")
    monkeypatch.setattr(handler, "_get_s3_client", lambda: fake)
    return fake


def test_process_batch_stores_one_object_for_all_capitals(s3, monkeypatch) -> None:
    monkeypatch.setattr(handler, "fetch_free_plan_weather", lambda job, api_key, timeout_seconds: current_weather_response("2026-06-25T12:00:00Z"))
    summary = handler.process_batch(_recent_job(), Context())
    assert summary["outcome"] == "stored"
    assert summary["collected"] == 2
    keys = s3.keys("bucket")
    assert keys == [summary["s3_key"]]
    stored = json.loads(s3.body("bucket", keys[0]))
    assert stored["format"] == "batch-v1"
    assert {item["job"]["state"] for item in stored["items"]} == {"SP", "RJ"}
    assert "secret" not in s3.body("bucket", keys[0]).decode("utf-8")
    assert handler.process_batch(_recent_job(), Context())["outcome"] == "duplicate"


@pytest.mark.parametrize("missing", ["RAW_DATA_BUCKET_NAME", "OPENWEATHER_API_KEY_PARAMETER_NAME"])
def test_process_batch_requires_configuration(s3, monkeypatch, missing) -> None:
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        handler.process_batch(_recent_job())


def test_expired_snapshot_is_skipped_without_calls(s3, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(handler, "fetch_free_plan_weather", lambda *args, **kwargs: calls.append(1))
    counters = handler.Counter()
    summary = handler.process_batch(_recent_job(minutes_ago=30), Context(), counters)
    assert summary["outcome"] == "expired"
    assert calls == []
    assert counters["SourceJobsExpired"] == 2
    assert s3.keys("bucket") == []


def test_unauthorized_response_drops_cached_key(s3, monkeypatch) -> None:
    resets = []
    monkeypatch.setattr(handler, "reset_api_key_cache", lambda: resets.append(True))

    def unauthorized(job, api_key, timeout_seconds):
        raise SourceError("openweather returned HTTP 401", retryable=True, status_code=401)

    monkeypatch.setattr(handler, "fetch_free_plan_weather", unauthorized)
    monkeypatch.setattr("shared.collection.time.sleep", lambda seconds: None)
    with pytest.raises(handler.BatchFailedError):
        handler.process_batch(_recent_job(("SP",)), Context())
    assert resets == [True, True, True]


def test_lambda_handler_reports_failures_and_emits_metrics(s3, monkeypatch, capsys) -> None:
    monkeypatch.delenv("METRICS_DISABLED", raising=False)
    monkeypatch.setattr("shared.collection.time.sleep", lambda seconds: None)

    def fetch(job, api_key, timeout_seconds):
        if job["product"] == "air_pollution":
            raise SourceError("openweather returned HTTP 503", retryable=True, status_code=503)
        if job["state"] == "RJ":
            raise SourceError("openweather returned HTTP 404", retryable=False, status_code=404)
        return current_weather_response("2026-06-25T12:00:00Z")

    monkeypatch.setattr(handler, "fetch_free_plan_weather", fetch)
    event = {
        "Records": [
            {"messageId": "weather", "body": json.dumps(_recent_job())},
            {"messageId": "air", "body": json.dumps(_recent_job(product="air_pollution"))},
            {"messageId": "broken", "body": "{not json"},
        ]
    }
    assert handler.lambda_handler(event, Context()) == {"batchItemFailures": [{"itemIdentifier": "air"}]}
    metrics = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{"_aws"')]
    assert metrics[-1]["OpenWeatherApiCalls"] == 2 + 6
    assert metrics[-1]["SourceJobsCollected"] == 1
    assert metrics[-1]["SourceJobsRejected"] == 2
    assert metrics[-1]["SourceJobFailures"] == 2


def test_batch_with_only_rejections_is_not_retried(s3, monkeypatch) -> None:
    def rejected(job, api_key, timeout_seconds):
        raise SourceError("openweather returned HTTP 404", retryable=False, status_code=404)

    monkeypatch.setattr(handler, "fetch_free_plan_weather", rejected)
    event = {"Records": [{"messageId": "m", "body": json.dumps(_recent_job(("SP",)))}]}
    assert handler.lambda_handler(event, Context()) == {"batchItemFailures": []}
