import os

from planner import handler


class FakeSqs:
    def __init__(self) -> None:
        self.messages = []

    def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return {"MessageId": "1"}


def test_plan_jobs_for_state_and_max_jobs(monkeypatch) -> None:
    monkeypatch.setattr(handler, "utc_snapshot", lambda value=None: "2026-06-25T12:00:00Z")
    jobs = handler.plan_jobs({"states": ["SP"], "products": ["current_weather", "forecast_5d_3h"], "max_jobs": 1})
    assert len(jobs) == 1
    assert jobs[0]["state"] == "SP"
    assert jobs[0]["snapshot_at"] == "2026-06-25T12:00:00Z"


def test_enqueue_jobs_uses_fifo_dedup(monkeypatch) -> None:
    fake = FakeSqs()
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: fake)
    count = handler.enqueue_jobs("queue", [{"state": "SP", "city": "Sao Paulo", "product": "current_weather", "snapshot_at": "2026-06-25T12:00:00Z"}])
    assert count == 1
    assert fake.messages[0]["MessageGroupId"] == "capital-SP"
    assert len(fake.messages[0]["MessageDeduplicationId"]) == 64


def test_lambda_handler_returns_planned_jobs(monkeypatch) -> None:
    fake = FakeSqs()
    monkeypatch.setattr(handler, "_get_sqs_client", lambda: fake)
    monkeypatch.setattr(handler, "utc_snapshot", lambda value=None: "2026-06-25T12:00:00Z")
    monkeypatch.setenv("COLLECTION_QUEUE_URL", "queue")
    result = handler.lambda_handler({"states": ["RJ"], "products": ["current_weather"]}, None)
    assert result["planned_jobs"] == 1
    assert result["snapshot_at"] == "2026-06-25T12:00:00Z"
    assert os.environ["COLLECTION_QUEUE_URL"] == "queue"
