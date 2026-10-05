import json

import pytest

from collector import handler
from shared.openweather import SourceError


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("RAW_DATA_BUCKET_NAME", "bucket")
    monkeypatch.setenv("OPENWEATHER_API_KEY_PARAMETER_NAME", "/param")
    monkeypatch.setattr(handler, "_get_ssm_client", lambda: object())
    monkeypatch.setattr(handler, "get_openweather_api_key", lambda ssm_client, parameter_name: "secret")
    monkeypatch.setattr(handler, "_get_s3_client", lambda: object())


def test_process_job_fetches_and_stores(monkeypatch) -> None:
    calls = {}
    monkeypatch.setattr(handler, "fetch_free_plan_weather", lambda job, api_key, timeout_seconds: {"dt": 1, "main": {}})

    def fake_put(s3_client, bucket, key, payload):
        calls.update({"bucket": bucket, "key": key, "payload": payload})
        return "stored"

    monkeypatch.setattr(handler, "put_json_once", fake_put)
    key, outcome = handler.process_job({"state": "SP", "city": "Sao Paulo", "product": "current_weather", "snapshot_at": "2026-06-25T12:00:00Z"})
    assert outcome == "stored"
    assert key.endswith("openweather_current_weather_sp_sao-paulo_20260625T1200Z.json")
    assert calls["payload"]["source"] == "openweather-free-plan"


@pytest.mark.parametrize("missing", ["RAW_DATA_BUCKET_NAME", "OPENWEATHER_API_KEY_PARAMETER_NAME"])
def test_process_job_requires_configuration(monkeypatch, missing) -> None:
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        handler.process_job({})


def test_unauthorized_response_drops_cached_key(monkeypatch) -> None:
    reset_calls = []
    monkeypatch.setattr(handler, "reset_api_key_cache", lambda: reset_calls.append(True))

    def unauthorized(job, api_key, timeout_seconds):
        raise SourceError("openweather returned HTTP 401", retryable=True, status_code=401)

    monkeypatch.setattr(handler, "fetch_free_plan_weather", unauthorized)
    with pytest.raises(SourceError):
        handler.process_job({"product": "current_weather"})
    assert reset_calls == [True]


def test_lambda_handler_uses_partial_batch_response_and_emits_metrics(monkeypatch, capsys) -> None:
    monkeypatch.delenv("METRICS_DISABLED", raising=False)

    def fake_process(job, counters):
        counters["OpenWeatherApiCalls"] += 1
        if job["city"] == "fail":
            raise RuntimeError("boom")
        return "key", "stored"

    monkeypatch.setattr(handler, "process_job", fake_process)
    event = {
        "Records": [
            {"messageId": "ok", "body": json.dumps({"city": "ok"})},
            {"messageId": "bad", "body": json.dumps({"city": "fail"})},
        ]
    }
    assert handler.lambda_handler(event, None) == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
    metrics = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{"_aws"')]
    assert metrics[-1]["OpenWeatherApiCalls"] == 2
    assert metrics[-1]["SourceJobsCollected"] == 1
    assert metrics[-1]["SourceJobFailures"] == 1


def test_lambda_handler_does_not_retry_non_retryable_source_error(monkeypatch) -> None:
    monkeypatch.setattr(handler, "process_job", lambda job, counters: (_ for _ in ()).throw(SourceError("bad data", retryable=False, status_code=404)))
    event = {"Records": [{"messageId": "bad", "body": json.dumps({"city": "bad"})}]}
    assert handler.lambda_handler(event, None) == {"batchItemFailures": []}


def test_lambda_handler_retries_retryable_source_error(monkeypatch) -> None:
    monkeypatch.setattr(handler, "process_job", lambda job, counters: (_ for _ in ()).throw(SourceError("timeout", retryable=True)))
    event = {"Records": [{"messageId": "bad", "body": json.dumps({"city": "bad"})}]}
    assert handler.lambda_handler(event, None) == {"batchItemFailures": [{"itemIdentifier": "bad"}]}


def test_lambda_handler_rejects_malformed_body_without_retry() -> None:
    event = {"Records": [{"messageId": "broken", "body": "{not json"}]}
    assert handler.lambda_handler(event, None) == {"batchItemFailures": []}
