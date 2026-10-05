from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3

from shared.call_budget import get_budget_status, record_planned_calls
from shared.capitals import get_capitals
from shared.source_plan import MONTHLY_OPERATIONAL_CALL_LIMIT, build_collection_jobs, parse_products, utc_snapshot
from shared.structured_logging import emit_metrics, log_event

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SQS_BATCH_SIZE = 10

_sqs_client = None
_cloudwatch_client = None


def _get_sqs_client():
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client("sqs")
    return _sqs_client


def _get_cloudwatch_client():
    global _cloudwatch_client
    if _cloudwatch_client is None:
        _cloudwatch_client = boto3.client("cloudwatch")
    return _cloudwatch_client


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
    for start in range(0, len(jobs), SQS_BATCH_SIZE):
        chunk = jobs[start : start + SQS_BATCH_SIZE]
        response = sqs.send_message_batch(
            QueueUrl=queue_url,
            Entries=[
                {
                    "Id": str(index),
                    "MessageBody": json.dumps(job, ensure_ascii=False, separators=(",", ":")),
                    "MessageGroupId": f"capital-{job['state']}",
                    "MessageDeduplicationId": _dedup_id(job),
                }
                for index, job in enumerate(chunk)
            ],
        )
        failed = response.get("Failed") or []
        if failed:
            codes = sorted({str(item.get("Code")) for item in failed})
            # Raising lets EventBridge retry; FIFO deduplication drops the messages that already went through.
            raise RuntimeError(f"failed to enqueue {len(failed)} collection jobs: {', '.join(codes)}")
    return len(jobs)


def _budget_allows(planned_calls: int, event: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    if os.getenv("CALL_BUDGET_ENFORCED", "true").lower() != "true" or event.get("skip_budget_check") is True:
        return True, None
    limit = int(os.getenv("MONTHLY_OPERATIONAL_CALL_LIMIT", str(MONTHLY_OPERATIONAL_CALL_LIMIT)))
    try:
        status = get_budget_status(_get_cloudwatch_client(), datetime.now(UTC), limit)
    except Exception:  # fail open: the operational limit is already half of the Free plan quota
        logger.warning("call_budget_unavailable", exc_info=True)
        return True, None
    return status.allows(planned_calls), status.as_dict()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    started = time.perf_counter()
    event = event or {}
    queue_url = os.getenv("COLLECTION_QUEUE_URL", "")
    if not queue_url:
        raise RuntimeError("COLLECTION_QUEUE_URL is not configured")
    jobs = plan_jobs(event)
    snapshot_at = jobs[0]["snapshot_at"] if jobs else None
    allowed, budget = _budget_allows(len(jobs), event)
    if not allowed:
        log_event(logger, logging.WARNING, "collection_jobs_skipped", jobs=len(jobs), budget=budget, outcome="monthly_call_limit")
        emit_metrics({"CollectionJobsSkipped": len(jobs)})
        return {"planned_jobs": 0, "skipped_jobs": len(jobs), "reason": "monthly_call_limit", "budget": budget, "snapshot_at": snapshot_at}

    enqueued = enqueue_jobs(queue_url, jobs)
    record_planned_calls(enqueued)
    log_event(
        logger,
        logging.INFO,
        "collection_jobs_planned",
        aws_request_id=getattr(context, "aws_request_id", None),
        jobs=enqueued,
        products=sorted({str(job["product"]) for job in jobs}),
        budget=budget,
        processing_time_ms=round((time.perf_counter() - started) * 1000),
        outcome="planned",
    )
    emit_metrics({"CollectionJobsPlanned": enqueued})
    return {"planned_jobs": enqueued, "skipped_jobs": 0, "snapshot_at": snapshot_at, "budget": budget}
