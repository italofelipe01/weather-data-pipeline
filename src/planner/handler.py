from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

import boto3

from shared.capitals import get_capitals
from shared.source_plan import build_collection_jobs, parse_products, utc_snapshot
from shared.structured_logging import log_count_metric, log_event

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_sqs_client = None


def _get_sqs_client():
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client("sqs")
    return _sqs_client


def _dedup_id(job: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(job, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def plan_jobs(event: dict[str, Any]) -> list[dict[str, object]]:
    units = str(event.get("units") or os.getenv("OPENWEATHER_UNITS", "metric"))
    lang = str(event.get("lang") or os.getenv("OPENWEATHER_LANG", "pt_br"))
    products = parse_products(event.get("products") or os.getenv("OPENWEATHER_PRODUCTS"))
    snapshot_at = utc_snapshot(event.get("snapshot_at"))
    states = event.get("states")
    if states is not None and not isinstance(states, list):
        raise ValueError("states must be a list of Brazilian UF codes")
    jobs = build_collection_jobs(get_capitals(states), products, units, lang, snapshot_at)
    max_jobs = event.get("max_jobs")
    if max_jobs is not None:
        jobs = jobs[: int(max_jobs)]
    return jobs


def enqueue_jobs(queue_url: str, jobs: list[dict[str, object]]) -> int:
    sqs = _get_sqs_client()
    for job in jobs:
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(job, ensure_ascii=False, separators=(",", ":")),
            MessageGroupId=f"capital-{job['state']}",
            MessageDeduplicationId=_dedup_id(job),
        )
    return len(jobs)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    started = time.perf_counter()
    queue_url = os.getenv("COLLECTION_QUEUE_URL", "")
    if not queue_url:
        raise RuntimeError("COLLECTION_QUEUE_URL is not configured")
    jobs = plan_jobs(event or {})
    enqueued = enqueue_jobs(queue_url, jobs)
    log_event(
        logger,
        logging.INFO,
        "collection_jobs_planned",
        aws_request_id=getattr(context, "aws_request_id", None),
        jobs=enqueued,
        processing_time_ms=round((time.perf_counter() - started) * 1000),
        outcome="planned",
    )
    log_count_metric(logger, "CollectionJobsPlanned", jobs=enqueued)
    return {"planned_jobs": enqueued, "snapshot_at": jobs[0]["snapshot_at"] if jobs else None}
