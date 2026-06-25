import json

from collector import handler
from shared.openweather import SourceError


def test_process_job_fetches_and_stores(monkeypatch) -> None:
    calls = {}
    monkeypatch.setenv("RAW_DATA_BUCKET_NAME", "bucket")
    monkeypatch.setenv("OPENWEATHER_API_KEY_PARAMETER_NAME", "/param")
    monkeypatch.setattr(handler, "_get_ssm_client", lambda: object())
    monkeypatch.setattr(handler, "get_openweather_api_key", lambda ssm_client, parameter_name: "secret")
    monkeypatch.setattr(handler, "fetch_free_plan_weather", lambda job, api_key, timeout_seconds: {"dt": 1, "main": {}})
    monkeypatch.setattr(handler, "_get_s3_client", lambda: object())

    def fake_put(s3_client, bucket, key, payload):
        calls["bucket"] = bucket
        calls["key"] = key
        calls["payload"] = payload
        return "stored"

    monkeypatch.setattr(handler, "put_json_once", fake_put)
    key, outcome = handler.process_job({"state": "SP", "city": "Sao Paulo", "product": "current_weather", "snapshot_at": "2026-06-25T12:00:00Z"})
    assert outcome == "stored"
    assert key.endswith("openweather_current_weather_sp_sao-paulo_20260625T1200Z.json")
    assert calls["payload"]["source"] == "openweather-free-plan"


def test_lambda_handler_uses_partial_batch_response(monkeypatch) -> None:
    def fake_process(job):
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


def test_lambda_handler_does_not_retry_non_retryable_source_error(monkeypatch) -> None:
    monkeypatch.setattr(handler, "process_job", lambda job: (_ for _ in ()).throw(SourceError("bad data", retryable=False)))
    event = {"Records": [{"messageId": "bad", "body": json.dumps({"city": "bad"})}]}
    assert handler.lambda_handler(event, None) == {"batchItemFailures": []}


def test_lambda_handler_retries_retryable_source_error(monkeypatch) -> None:
    monkeypatch.setattr(handler, "process_job", lambda job: (_ for _ in ()).throw(SourceError("timeout", retryable=True)))
    event = {"Records": [{"messageId": "bad", "body": json.dumps({"city": "bad"})}]}
    assert handler.lambda_handler(event, None) == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
