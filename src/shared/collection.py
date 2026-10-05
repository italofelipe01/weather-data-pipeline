"""Collect one product snapshot for many capitals and pack every response into a single raw object.

One object per snapshot (instead of one per capital) cuts S3 PUT requests ~27x, which is what keeps the
AWS bill near zero. The same code runs in the Collector Lambda and in the offline service.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from shared.capitals import Capital
from shared.openweather import SourceError
from shared.storage import build_raw_hour_prefix, sanitize_component
from shared.time_utils import iso_z, parse_utc

BATCH_FORMAT = "batch-v1"
SOURCE = "openweather-free-plan"
SOURCE_TERMS = "OpenWeather Free plan: 60 calls/minute and 1,000,000 calls/month."
SOURCE_URL = "https://openweathermap.org/price"

# Snapshots older than this are skipped instead of collected: the API returns *current* data, so a late
# retry would store today's values under an old timestamp.
MAX_SNAPSHOT_AGE_SECONDS = {
    "current_weather": 15 * 60,
    "air_pollution": 90 * 60,
    "forecast_5d_3h": 90 * 60,
    "air_pollution_forecast": 6 * 3600,
}
CAPITAL_FIELDS = ("city", "state", "ibge_code", "latitude", "longitude", "timezone")


def build_batch_job(product: str, capitals: Iterable[Capital], units: str, lang: str, snapshot_at: str) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "format": BATCH_FORMAT,
        "product": product,
        "snapshot_at": snapshot_at,
        "units": units,
        "lang": lang,
        "capitals": [{field_name: capital[field_name] for field_name in CAPITAL_FIELDS} for capital in capitals],
    }


def capital_jobs(batch_job: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-capital jobs, in the same shape the per-capital collector used (kept inside raw objects)."""
    common = {
        "source": batch_job.get("source", SOURCE),
        "product": batch_job["product"],
        "snapshot_at": batch_job["snapshot_at"],
        "units": batch_job.get("units", "metric"),
        "lang": batch_job.get("lang", "pt_br"),
    }
    return [
        {
            "source": common["source"],
            "product": common["product"],
            **{field_name: capital.get(field_name) for field_name in CAPITAL_FIELDS},
            "snapshot_at": common["snapshot_at"],
            "units": common["units"],
            "lang": common["lang"],
        }
        for capital in batch_job.get("capitals", [])
    ]


def build_batch_key(product: str, snapshot_at: str, states: Iterable[str]) -> str:
    snapshot = parse_utc(snapshot_at)
    states_hash = hashlib.sha256(",".join(sorted(str(state).upper() for state in states)).encode("utf-8")).hexdigest()[:8]
    product_component = sanitize_component(product)
    return f"{build_raw_hour_prefix(product, snapshot)}openweather_{product_component}_{snapshot:%Y%m%dT%H%MZ}_{states_hash}.json"


def snapshot_age_seconds(batch_job: dict[str, Any], now: datetime | None = None) -> float:
    return ((now or datetime.now(UTC)) - parse_utc(batch_job["snapshot_at"])).total_seconds()


def is_expired(batch_job: dict[str, Any], now: datetime | None = None) -> bool:
    limit = MAX_SNAPSHOT_AGE_SECONDS.get(str(batch_job.get("product")), 3600)
    return snapshot_age_seconds(batch_job, now) > limit


@dataclass
class CollectionResult:
    product: str
    snapshot_at: str
    items: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    calls: int = 0

    @property
    def requested(self) -> int:
        return len(self.items) + len(self.failures) + len(self.rejected)

    def raw_object(self) -> dict[str, Any]:
        return {
            "source": SOURCE,
            "format": BATCH_FORMAT,
            "source_terms": SOURCE_TERMS,
            "source_url": SOURCE_URL,
            "product": self.product,
            "snapshot_at": self.snapshot_at,
            "retrieved_at": iso_z(datetime.now(UTC)),
            "items": self.items,
            "failures": [*self.failures, *self.rejected],
        }


def _response_hash(response: dict[str, Any]) -> str:
    canonical = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def collect_batch(
    batch_job: dict[str, Any],
    fetch: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    min_interval: float = 0.0,
    max_attempts: int = 3,
    backoff_seconds: tuple[float, ...] = (2.0, 5.0),
    remaining_seconds: Callable[[], float] | None = None,
    reserve_seconds: float = 20.0,
    on_unauthorized: Callable[[], None] | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> CollectionResult:
    """Fetch every capital sequentially, spaced by `min_interval`, retrying transient errors in-process."""
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    result = CollectionResult(product=str(batch_job["product"]), snapshot_at=str(batch_job["snapshot_at"]))
    last_call: float | None = None
    for job in capital_jobs(batch_job):
        state = str(job.get("state"))
        if remaining_seconds is not None and remaining_seconds() < reserve_seconds:
            result.failures.append({"state": state, "error": "time budget exhausted", "status_code": None})
            continue
        for attempt in range(1, max_attempts + 1):
            if last_call is not None and min_interval > 0:
                wait = min_interval - (clock() - last_call)
                if wait > 0:
                    sleep(wait)
            last_call = clock()
            result.calls += 1
            try:
                response = fetch(job)
            except SourceError as exc:
                if exc.status_code == 401 and on_unauthorized is not None:
                    on_unauthorized()
                if not exc.retryable:
                    result.rejected.append({"state": state, "error": str(exc), "status_code": exc.status_code})
                    break
                if attempt == max_attempts:
                    result.failures.append({"state": state, "error": str(exc), "status_code": exc.status_code})
                    break
                sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
                continue
            result.items.append({"job": job, "retrieved_at": iso_z(datetime.now(UTC)), "response_hash": _response_hash(response), "response": response})
            break
    return result
