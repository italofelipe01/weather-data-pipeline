import json

import pytest
from botocore.exceptions import ClientError

from planner import handler


class FakeSqs:
    def __init__(self, fail_codes: list[str] | None = None) -> None:
        self.batches = []
        self.fail_codes = fail_codes or []

    def send_message_batch(self, **kwargs):
        self.batches.append(kwargs)
        failed = [{"Id": entry["Id"], "Code": code} for entry, code in zip(kwargs["Entries"], self.fail_codes, strict=False)]
        return {"Successful": [], "Failed": failed}

    @property
    def entries(self):
        return [entry for batch in self.batches for entry in batch["Entries"]]


class FakeSsm:
    def __init__(self, calls: int = 0, month: str | None = None, broken: bool = False) -> None:
        from datetime import UTC, datetime

        self.value = json.dumps({"month": month or f"{datetime.now(UTC):%Y-%m}", "calls": calls})
        self.broken = broken

    def get_parameter(self, **kwargs):
        if self.broken:
            raise ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetParameter")
        return {"Parameter": {"Value": self.value}}

    def put_parameter(self, **kwargs):
        self.value = kwargs["Value"]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("COLLECTION_QUEUE_URL", "queue")
    monkeypatch.setenv("CALL_COUNTER_PARAMETER_NAME", "/stack/openweather-call-counter")
    monkeypatch.setenv("METRICS_DISABLED", "true")
    monkeypatch.setattr(handler, "utc_snapshot", lambda value=None: "2026-06-25T12:00:00Z")


def test_plan_jobs_creates_one_batch_per_product() -> None:
    jobs = handler.plan_jobs({"states": ["SP", "RJ"], "products": ["current_weather", "forecast_5d_3h"]})
    assert [job["product"] for job in jobs] == ["current_weather", "forecast_5d_3h"]
    assert {capital["state"] for capital in jobs[0]["capitals"]} == {"SP", "RJ"}
    assert jobs[0]["snapshot_at"] == "2026-06-25T12:00:00Z"
    assert handler.planned_calls(jobs) == 4
    assert handler.planned_calls(handler.plan_jobs({"products": "all"})) == 108


def test_plan_jobs_validates_states() -> None:
    with pytest.raises(ValueError, match="list"):
        handler.plan_jobs({"states": "SP"})
    with pytest.raises(ValueError, match="XX"):
        handler.plan_jobs({"states": ["XX"]})


def test_enqueue_jobs_uses_one_fifo_group_per_product(monkeypatch) -> None:
    fake = FakeSqs()
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: fake)
    jobs = handler.plan_jobs({"products": "all"})
    assert handler.enqueue_jobs("queue", jobs) == 4
    assert [entry["MessageGroupId"] for entry in fake.entries] == [
        "product-current_weather",
        "product-forecast_5d_3h",
        "product-air_pollution",
        "product-air_pollution_forecast",
    ]
    assert len(fake.entries[0]["MessageDeduplicationId"]) == 64
    body = json.loads(fake.entries[0]["MessageBody"])
    assert len(body["capitals"]) == 27
    assert len(fake.entries[0]["MessageBody"].encode("utf-8")) < 16_000


def test_enqueue_jobs_raises_on_partial_failure(monkeypatch) -> None:
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: FakeSqs(["ThrottlingException"]))
    with pytest.raises(RuntimeError, match="ThrottlingException"):
        handler.enqueue_jobs("queue", handler.plan_jobs({"states": ["SP"]}))


def test_lambda_handler_plans_and_counts_calls(monkeypatch) -> None:
    sqs, ssm = FakeSqs(), FakeSsm(1000)
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: sqs)
    monkeypatch.setattr(handler, "_get_ssm_client", lambda: ssm)
    result = handler.lambda_handler({"states": ["RJ"], "products": ["current_weather"]}, None)
    assert result["planned_jobs"] == 1
    assert result["planned_calls"] == 1
    assert result["budget"]["calls_month_to_date"] == 1000
    assert json.loads(ssm.value)["calls"] == 1001


def test_lambda_handler_skips_when_monthly_limit_would_be_exceeded(monkeypatch) -> None:
    sqs, ssm = FakeSqs(), FakeSsm(499_990)
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: sqs)
    monkeypatch.setattr(handler, "_get_ssm_client", lambda: ssm)
    monkeypatch.setenv("MONTHLY_OPERATIONAL_CALL_LIMIT", "500000")
    result = handler.lambda_handler({"products": ["current_weather"]}, None)
    assert result["planned_jobs"] == 0
    assert result["skipped_calls"] == 27
    assert result["reason"] == "monthly_call_limit"
    assert sqs.batches == []
    forced = handler.lambda_handler({"products": ["current_weather"], "skip_budget_check": True}, None)
    assert forced["planned_calls"] == 27


def test_lambda_handler_fails_open_without_counter(monkeypatch) -> None:
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: FakeSqs())
    monkeypatch.setattr(handler, "_get_ssm_client", lambda: FakeSsm(broken=True))
    assert handler.lambda_handler({"states": ["SP"]}, None)["planned_jobs"] == 1
    monkeypatch.delenv("CALL_COUNTER_PARAMETER_NAME")
    assert handler.lambda_handler({"states": ["SP"]}, None)["budget"] is None


def test_lambda_handler_requires_queue(monkeypatch) -> None:
    monkeypatch.delenv("COLLECTION_QUEUE_URL")
    with pytest.raises(RuntimeError, match="COLLECTION_QUEUE_URL"):
        handler.lambda_handler({}, None)
