import json
from datetime import UTC, datetime

from botocore.exceptions import ClientError

from shared.call_budget import FileCallCounter, SsmCallCounter, budget_status


class FakeSsm:
    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.puts = []

    def get_parameter(self, **kwargs):
        if self.value is None:
            raise ClientError({"Error": {"Code": "ParameterNotFound"}}, "GetParameter")
        return {"Parameter": {"Value": self.value}}

    def put_parameter(self, **kwargs):
        self.puts.append(kwargs)
        self.value = kwargs["Value"]


def test_budget_status_projects_the_month() -> None:
    status = budget_status(100_000, 500_000, datetime(2026, 6, 11, tzinfo=UTC))
    assert status.projected == 300_000
    assert status.allows(400_000) is True
    assert status.allows(400_001) is False
    summary = status.as_dict()
    assert summary["remaining"] == 400_000
    assert summary["month"] == "2026-06"
    assert summary["usage_ratio"] == 0.2


def test_ssm_counter_accumulates_and_resets_each_month() -> None:
    ssm = FakeSsm()
    counter = SsmCallCounter(ssm, "/stack/openweather-call-counter")
    june = datetime(2026, 6, 30, 23, tzinfo=UTC)
    assert counter.read(june) == 0
    assert counter.add(june, 27) == 27
    assert counter.add(june, 27) == 54
    assert ssm.puts[-1]["Type"] == "String" and ssm.puts[-1]["Overwrite"] is True
    assert json.loads(ssm.value) == {"month": "2026-06", "calls": 54}
    july = datetime(2026, 7, 1, 0, 3, tzinfo=UTC)
    assert counter.read(july) == 0
    assert counter.add(july, 27) == 27


def test_ssm_counter_tolerates_initial_or_corrupt_values() -> None:
    assert SsmCallCounter(FakeSsm('{"month":"","calls":0}'), "/p").read(datetime(2026, 6, 1, tzinfo=UTC)) == 0
    assert SsmCallCounter(FakeSsm("not json"), "/p").read(datetime(2026, 6, 1, tzinfo=UTC)) == 0


def test_ssm_counter_propagates_other_errors() -> None:
    class Denied(FakeSsm):
        def get_parameter(self, **kwargs):
            raise ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetParameter")

    try:
        SsmCallCounter(Denied(), "/p").read(datetime(2026, 6, 1, tzinfo=UTC))
    except ClientError:
        pass
    else:
        raise AssertionError("expected ClientError")


def test_file_counter(tmp_path) -> None:
    counter = FileCallCounter(tmp_path / "state" / "calls.json")
    now = datetime(2026, 6, 10, tzinfo=UTC)
    assert counter.read(now) == 0
    counter.add(now, 108)
    assert FileCallCounter(tmp_path / "state" / "calls.json").read(now) == 108
    assert counter.read(datetime(2026, 7, 1, tzinfo=UTC)) == 0
