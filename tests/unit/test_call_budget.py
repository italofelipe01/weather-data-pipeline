from datetime import UTC, datetime

import pytest

from shared import call_budget


class FakeCloudWatch:
    def __init__(self, pages: list[list[float]]) -> None:
        self.pages = pages
        self.calls = []

    def get_metric_data(self, **kwargs):
        self.calls.append(kwargs)
        index = len(self.calls) - 1
        response = {"MetricDataResults": [{"Id": "calls", "Values": self.pages[index]}]}
        if index + 1 < len(self.pages):
            response["NextToken"] = str(index + 1)
        return response


@pytest.fixture(autouse=True)
def _reset_cache():
    call_budget.reset_cache()
    yield
    call_budget.reset_cache()


def test_query_sums_all_pages_from_month_start() -> None:
    fake = FakeCloudWatch([[1000.0, 2000.0], [500.0]])
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)
    assert call_budget.query_month_to_date_calls(fake, "pipeline", now) == 3500
    query = fake.calls[0]
    assert query["StartTime"] == datetime(2026, 6, 1, tzinfo=UTC)
    stat = query["MetricDataQueries"][0]["MetricStat"]
    assert stat["Metric"]["MetricName"] == "OpenWeatherApiCalls"
    assert stat["Metric"]["Dimensions"] == [{"Name": "Pipeline", "Value": "pipeline"}]
    assert fake.calls[1]["NextToken"] == "1"


def test_budget_status_is_cached_and_tracks_planned_calls() -> None:
    fake = FakeCloudWatch([[100_000.0]])
    now = datetime(2026, 6, 11, tzinfo=UTC)
    status = call_budget.get_budget_status(fake, now, limit=500_000, pipeline="p", cache_seconds=300)
    assert status.used == 100_000
    assert status.projected == 300_000
    assert status.allows(400_000) is True
    assert status.allows(400_001) is False
    call_budget.record_planned_calls(27)
    again = call_budget.get_budget_status(fake, now, limit=500_000, pipeline="p", cache_seconds=300)
    assert again.used == 100_027
    assert len(fake.calls) == 1
    summary = again.as_dict()
    assert summary["remaining"] == 399_973
    assert summary["month"] == "2026-06"


class SequenceCloudWatch:
    def __init__(self, totals: list[float]) -> None:
        self.totals = totals
        self.calls = []

    def get_metric_data(self, **kwargs):
        self.calls.append(kwargs)
        return {"MetricDataResults": [{"Values": [self.totals[len(self.calls) - 1]]}]}


def test_month_change_invalidates_cache() -> None:
    fake = SequenceCloudWatch([10.0, 0.0])
    call_budget.get_budget_status(fake, datetime(2026, 6, 30, 23, tzinfo=UTC), limit=10, pipeline="p", cache_seconds=300)
    status = call_budget.get_budget_status(fake, datetime(2026, 7, 1, 0, 5, tzinfo=UTC), limit=10, pipeline="p", cache_seconds=300)
    assert status.used == 0
    assert status.allows(10) is True
    assert len(fake.calls) == 2
