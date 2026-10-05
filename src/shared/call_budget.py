from __future__ import annotations

import calendar
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from shared.structured_logging import DEFAULT_NAMESPACE
from shared.time_utils import month_start, parse_utc

API_CALLS_METRIC = "OpenWeatherApiCalls"

_cache: dict[str, Any] = {"month": None, "value": None, "until": 0.0, "added": 0}


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


def reset_cache() -> None:
    _cache.update({"month": None, "value": None, "until": 0.0, "added": 0})


def query_month_to_date_calls(cloudwatch_client: Any, pipeline: str, now: datetime, namespace: str = DEFAULT_NAMESPACE) -> int:
    start = month_start(now)
    total = 0.0
    next_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "MetricDataQueries": [
                {
                    "Id": "calls",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": namespace,
                            "MetricName": API_CALLS_METRIC,
                            "Dimensions": [{"Name": "Pipeline", "Value": pipeline}],
                        },
                        "Period": 86400,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            ],
            "StartTime": start,
            "EndTime": parse_utc(now) + timedelta(minutes=1),
        }
        if next_token:
            kwargs["NextToken"] = next_token
        response = cloudwatch_client.get_metric_data(**kwargs)
        for result in response.get("MetricDataResults", []):
            total += sum(float(value) for value in result.get("Values", []))
        next_token = response.get("NextToken")
        if not next_token:
            return int(total)


def get_budget_status(cloudwatch_client: Any, now: datetime, limit: int, pipeline: str | None = None, cache_seconds: int | None = None) -> BudgetStatus:
    """Month-to-date OpenWeather calls (from the Collector EMF metric), cached briefly per Lambda container."""
    now = parse_utc(now)
    pipeline = pipeline or os.getenv("PIPELINE_NAME", "local")
    namespace = os.getenv("METRICS_NAMESPACE", DEFAULT_NAMESPACE)
    ttl = int(os.getenv("CALL_BUDGET_CACHE_SECONDS", "300")) if cache_seconds is None else cache_seconds
    month = f"{now:%Y-%m}"
    if _cache["month"] != month or _cache["value"] is None or time.monotonic() >= _cache["until"]:
        _cache.update(
            {"month": month, "value": query_month_to_date_calls(cloudwatch_client, pipeline, now, namespace), "until": time.monotonic() + ttl, "added": 0}
        )
    used = int(_cache["value"]) + int(_cache["added"])
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed_days = max((now - month_start(now)).total_seconds() / 86400, 1 / 24)
    projected = int(used / elapsed_days * days_in_month)
    return BudgetStatus(month=month, used=used, limit=limit, projected=projected)


def record_planned_calls(count: int) -> None:
    """Account calls enqueued since the last CloudWatch read, so the cached value stays conservative."""
    _cache["added"] = int(_cache["added"]) + count
