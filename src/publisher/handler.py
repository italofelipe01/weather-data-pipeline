from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import boto3

from shared.call_budget import CallCounter, SsmCallCounter, budget_status
from shared.capitals import BRAZIL_CAPITALS
from shared.observations import extract_air_pollution, extract_current_weather
from shared.raw_reader import latest_by_state
from shared.s3_io import put_json, read_json
from shared.serving import LATEST_CACHE_CONTROL, LATEST_KEY, build_latest_payload
from shared.source_plan import MONTHLY_OPERATIONAL_CALL_LIMIT
from shared.structured_logging import log_event

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3_client = None
_ssm_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _get_ssm_client():
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


@dataclass(frozen=True)
class PublisherConfig:
    raw_bucket: str
    site_bucket: str
    lookback_hours: int = 3
    call_limit: int = MONTHLY_OPERATIONAL_CALL_LIMIT
    runtime: str = "aws"

    @classmethod
    def from_env(cls) -> PublisherConfig:
        raw_bucket = os.getenv("RAW_DATA_BUCKET_NAME", "")
        site_bucket = os.getenv("SITE_BUCKET_NAME", "")
        if not raw_bucket or not site_bucket:
            raise RuntimeError("RAW_DATA_BUCKET_NAME and SITE_BUCKET_NAME must be configured")
        return cls(
            raw_bucket=raw_bucket,
            site_bucket=site_bucket,
            lookback_hours=int(os.getenv("LATEST_LOOKBACK_HOURS", "3")),
            call_limit=int(os.getenv("MONTHLY_OPERATIONAL_CALL_LIMIT", str(MONTHLY_OPERATIONAL_CALL_LIMIT))),
        )


def publish_latest(s3_client: Any, config: PublisherConfig, now: datetime | None = None, counter: CallCounter | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    expected = len(BRAZIL_CAPITALS)
    current = latest_by_state(s3_client, config.raw_bucket, "current_weather", now, config.lookback_hours, extract_current_weather, expected)
    air = latest_by_state(s3_client, config.raw_bucket, "air_pollution", now, config.lookback_hours, extract_air_pollution, expected)
    budget = None
    if counter is not None:
        try:
            budget = budget_status(counter.read(now), config.call_limit, now).as_dict()
        except Exception:
            logger.warning("call_counter_unavailable", exc_info=True)
    previous = read_json(s3_client, config.site_bucket, LATEST_KEY)
    products = [name for name, found in (("current_weather", current), ("air_pollution", air)) if found]
    payload = build_latest_payload(current, air, now, budget, previous, products)
    payload["runtime"] = config.runtime
    put_json(s3_client, config.site_bucket, LATEST_KEY, payload, LATEST_CACHE_CONTROL)
    return {
        "key": LATEST_KEY,
        "current_capitals": len(current),
        "air_capitals": len(air),
        "latest_observation_at": payload["latest_observation_at"],
        "budget": budget,
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    started = time.perf_counter()
    parameter_name = os.getenv("CALL_COUNTER_PARAMETER_NAME", "")
    counter = SsmCallCounter(_get_ssm_client(), parameter_name) if parameter_name else None
    result = publish_latest(_get_s3_client(), PublisherConfig.from_env(), counter=counter)
    log_event(
        logger,
        logging.INFO,
        "latest_published",
        aws_request_id=getattr(context, "aws_request_id", None),
        **result,
        processing_time_ms=round((time.perf_counter() - started) * 1000),
        outcome="published",
    )
    return result
