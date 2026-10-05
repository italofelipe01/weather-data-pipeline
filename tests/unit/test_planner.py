import json

import pytest

from planner import handler
from shared import call_budget


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


class FakeCloudWatch:
    def __init__(self, used: float) -> None:
        self.used = used

    def get_metric_data(self, **kwargs):
        return {"MetricDataResults": [{"Values": [self.used]}]}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    call_budget.reset_cache()
    monkeypatch.setenv("COLLECTION_QUEUE_URL", "queue")
    monkeypatch.setenv("METRICS_DISABLED", "true")
    monkeypatch.setattr(handler, "utc_snapshot", lambda value=None: "2026-06-25T12:00:00Z")
    yield
    call_budget.reset_cache()


def test_plan_jobs_for_state_and_max_jobs() -> None:
    jobs = handler.plan_jobs({"states": ["SP"], "products": ["current_weather", "forecast_5d_3h"], "max_jobs": 1})
    assert len(jobs) == 1
    assert jobs[0]["state"] == "SP"
    assert jobs[0]["snapshot_at"] == "2026-06-25T12:00:00Z"


def test_plan_jobs_validates_states() -> None:
    with pytest.raises(ValueError, match="list"):
        handler.plan_jobs({"states": "SP"})
    with pytest.raises(ValueError, match="XX"):
        handler.plan_jobs({"states": ["XX"]})


def test_enqueue_jobs_uses_fifo_batches(monkeypatch) -> None:
    fake = FakeSqs()
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: fake)
    jobs = handler.plan_jobs({"products": ["current_weather"]})
    assert handler.enqueue_jobs("queue", jobs) == 27
    assert [len(batch["Entries"]) for batch in fake.batches] == [10, 10, 7]
    first = fake.entries[0]
    assert first["MessageGroupId"] == f"capital-{jobs[0]['state']}"
    assert len(first["MessageDeduplicationId"]) == 64
    assert json.loads(first["MessageBody"])["product"] == "current_weather"


def test_enqueue_jobs_raises_on_partial_failure(monkeypatch) -> None:
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: FakeSqs(["ThrottlingException"]))
    with pytest.raises(RuntimeError, match="ThrottlingException"):
        handler.enqueue_jobs("queue", handler.plan_jobs({"states": ["SP"]}))


def test_lambda_handler_returns_planned_jobs(monkeypatch) -> None:
    fake = FakeSqs()
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: fake)
    monkeypatch.setattr(handler, "_get_cloudwatch_client", lambda: FakeCloudWatch(1000))
    result = handler.lambda_handler({"states": ["RJ"], "products": ["current_weather"]}, None)
    assert result["planned_jobs"] == 1
    assert result["snapshot_at"] == "2026-06-25T12:00:00Z"
    assert result["budget"]["calls_month_to_date"] == 1000


def test_lambda_handler_skips_when_monthly_limit_would_be_exceeded(monkeypatch) -> None:
    fake = FakeSqs()
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: fake)
    monkeypatch.setattr(handler, "_get_cloudwatch_client", lambda: FakeCloudWatch(499_990))
    monkeypatch.setenv("MONTHLY_OPERATIONAL_CALL_LIMIT", "500000")
    result = handler.lambda_handler({"products": ["current_weather"]}, None)
    assert result["planned_jobs"] == 0
    assert result["skipped_jobs"] == 27
    assert result["reason"] == "monthly_call_limit"
    assert fake.batches == []
    forced = handler.lambda_handler({"products": ["current_weather"], "skip_budget_check": True}, None)
    assert forced["planned_jobs"] == 27


def test_lambda_handler_fails_open_when_cloudwatch_is_unavailable(monkeypatch) -> None:
    class Broken:
        def get_metric_data(self, **kwargs):
            raise RuntimeError("denied")

    monkeypatch.setattr(handler, "_get_sqs_client", lambda: FakeSqs())
    monkeypatch.setattr(handler, "_get_cloudwatch_client", lambda: Broken())
    assert handler.lambda_handler({"states": ["SP"]}, None)["planned_jobs"] == 1


def test_lambda_handler_requires_queue(monkeypatch) -> None:
    monkeypatch.delenv("COLLECTION_QUEUE_URL")
    with pytest.raises(RuntimeError, match="COLLECTION_QUEUE_URL"):
        handler.lambda_handler({}, None)
