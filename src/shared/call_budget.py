"""Month-to-date OpenWeather call counter used to enforce MonthlyOperationalCallLimit.

The Planner adds the calls it schedules; the Publisher reads the value for the dashboard. Two free backends:
an SSM standard String parameter (cloud) and a JSON file (offline). CloudWatch GetMetricData is not used
because it is billed per metric requested and has no free allowance.
"""

from __future__ import annotations

import calendar
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from botocore.exceptions import ClientError

from shared.time_utils import month_start, parse_utc


@dataclass(frozen=True)
class BudgetStatus:
    month: str
    used: int
    limit: int
    projected: int

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)

    def allows(self, planned_calls: int) -> bool:
        return self.used + planned_calls <= self.limit

    def as_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "calls_month_to_date": self.used,
            "operational_limit": self.limit,
            "remaining": self.remaining,
            "projected_month_total": self.projected,
            "usage_ratio": round(self.used / self.limit, 4) if self.limit else None,
        }


def month_key(now: datetime) -> str:
    return f"{parse_utc(now):%Y-%m}"


def budget_status(used: int, limit: int, now: datetime) -> BudgetStatus:
    now = parse_utc(now)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed_days = max((now - month_start(now)).total_seconds() / 86400, 1 / 24)
    return BudgetStatus(month=month_key(now), used=used, limit=limit, projected=int(used / elapsed_days * days_in_month))


class CallCounter(Protocol):
    def read(self, now: datetime) -> int: ...

    def add(self, now: datetime, calls: int) -> int: ...


def _decode(value: str | None, now: datetime) -> int:
    try:
        document = json.loads(value or "{}")
    except json.JSONDecodeError:
        return 0
    if not isinstance(document, dict) or document.get("month") != month_key(now):
        return 0  # a new month starts from zero
    return int(document.get("calls") or 0)


def _encode(now: datetime, calls: int) -> str:
    return json.dumps({"month": month_key(now), "calls": calls}, separators=(",", ":"))


class SsmCallCounter:
    """Standard-tier String parameter: no storage or API charge. Read-modify-write; the rare race between two
    Planner runs can only undercount a few calls, which the 50% safety margin absorbs."""

    def __init__(self, ssm_client: Any, parameter_name: str) -> None:
        self.ssm_client = ssm_client
        self.parameter_name = parameter_name

    def read(self, now: datetime) -> int:
        try:
            response = self.ssm_client.get_parameter(Name=self.parameter_name)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ParameterNotFound":
                return 0
            raise
        return _decode(response.get("Parameter", {}).get("Value"), now)

    def add(self, now: datetime, calls: int) -> int:
        total = self.read(now) + calls
        self.ssm_client.put_parameter(Name=self.parameter_name, Value=_encode(now, total), Type="String", Overwrite=True)
        return total


class FileCallCounter:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read(self, now: datetime) -> int:
        try:
            return _decode(self.path.read_text(encoding="utf-8"), now)
        except FileNotFoundError:
            return 0

    def add(self, now: datetime, calls: int) -> int:
        total = self.read(now) + calls
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp") as handle:
            handle.write(_encode(now, total))
        os.replace(handle.name, self.path)
        return total
