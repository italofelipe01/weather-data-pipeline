from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import boto3

from shared.call_budget import get_budget_status
from shared.capitals import BRAZIL_CAPITALS
from shared.observations import extract_air_pollution, extract_current_weather
from shared.s3_io import parallel_map, put_json, read_bytes, read_json
from shared.serving import LATEST_CACHE_CONTROL, LATEST_KEY, build_latest_payload
from shared.source_plan import MONTHLY_OPERATIONAL_CALL_LIMIT
from shared.storage import find_latest_raw_keys
from shared.structured_logging import log_event

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3_client = None
_cloudwatch_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _get_cloudwatch_client():
    global _cloudwatch_client
    if _cloudwatch_client is None:
        _cloudwatch_client = boto3.client("cloudwatch")
    return _cloudwatch_client


@dataclass(frozen=True)
class PublisherConfig:
    raw_bucket: str
    site_bucket: str
    lookback_hours: int = 3
    call_limit: int = MONTHLY_OPERATIONAL_CALL_LIMIT
    max_workers: int = 16

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


def _latest_by_state(s3_client: Any, config: PublisherConfig, product: str, extractor: Any, now: datetime) -> dict[str, dict[str, Any]]:
    keys = find_latest_raw_keys(s3_client, config.raw_bucket, product, now, config.lookback_hours, len(BRAZIL_CAPITALS))
    bodies = parallel_map(lambda key: read_bytes(s3_client, config.raw_bucket, key), list(keys.values()), config.max_workers)
    extracted = [extractor(json.loads(body.decode("utf-8"))) for body in bodies if body is not None]
    return {item["state"]: item for item in extracted if item is not None}


def publish_latest(s3_client: Any, config: PublisherConfig, now: datetime | None = None, cloudwatch_client: Any | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    current = _latest_by_state(s3_client, config, "current_weather", extract_current_weather, now)
    air = _latest_by_state(s3_client, config, "air_pollution", extract_air_pollution, now)
    budget = None
    if cloudwatch_client is not None:
        try:
            budget = get_budget_status(cloudwatch_client, now, config.call_limit).as_dict()
        except Exception:
            logger.warning("call_budget_unavailable", exc_info=True)
    previous = read_json(s3_client, config.site_bucket, LATEST_KEY)
    products = [name for name, found in (("current_weather", current), ("air_pollution", air)) if found]
    payload = build_latest_payload(current, air, now, budget, previous, products)
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
    result = publish_latest(_get_s3_client(), PublisherConfig.from_env(), cloudwatch_client=_get_cloudwatch_client())
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
