from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3

from shared.call_budget import SsmCallCounter, budget_status
from shared.capitals import get_capitals
from shared.collection import build_batch_job
from shared.source_plan import MONTHLY_OPERATIONAL_CALL_LIMIT, parse_products, utc_snapshot
from shared.structured_logging import emit_metrics, log_event

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SQS_BATCH_SIZE = 10

_sqs_client = None
_ssm_client = None


def _get_sqs_client():
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client("sqs")
    return _sqs_client


def _get_ssm_client():
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


def _dedup_id(job: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(job, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def plan_jobs(event: dict[str, Any]) -> list[dict[str, Any]]:
    """One batch job per product, each listing every capital to collect."""
    units = str(event.get("units") or os.getenv("OPENWEATHER_UNITS", "metric"))
    lang = str(event.get("lang") or os.getenv("OPENWEATHER_LANG", "pt_br"))
    products = parse_products(event.get("products") or os.getenv("OPENWEATHER_PRODUCTS"))
    snapshot_at = utc_snapshot(event.get("snapshot_at"))
    states = event.get("states")
    if states is not None and not isinstance(states, list):
        raise ValueError("states must be a list of Brazilian UF codes")
    capitals = get_capitals(states)
    return [build_batch_job(product, capitals, units, lang, snapshot_at) for product in products]


def planned_calls(jobs: list[dict[str, Any]]) -> int:
    return sum(len(job["capitals"]) for job in jobs)


def enqueue_jobs(queue_url: str, jobs: list[dict[str, Any]]) -> int:
    sqs = _get_sqs_client()
    for start in range(0, len(jobs), SQS_BATCH_SIZE):
        chunk = jobs[start : start + SQS_BATCH_SIZE]
        response = sqs.send_message_batch(
            QueueUrl=queue_url,
            Entries=[
                {
                    "Id": str(index),
                    "MessageBody": json.dumps(job, ensure_ascii=False, separators=(",", ":")),
                    # One group per product: products may run in parallel, snapshots of a product run in order.
                    "MessageGroupId": f"product-{job['product']}",
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


def _counter() -> SsmCallCounter | None:
    parameter_name = os.getenv("CALL_COUNTER_PARAMETER_NAME", "")
    return SsmCallCounter(_get_ssm_client(), parameter_name) if parameter_name else None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    started = time.perf_counter()
    event = event or {}
    queue_url = os.getenv("COLLECTION_QUEUE_URL", "")
    if not queue_url:
        raise RuntimeError("COLLECTION_QUEUE_URL is not configured")
    jobs = plan_jobs(event)
    calls = planned_calls(jobs)
    snapshot_at = jobs[0]["snapshot_at"] if jobs else None
    now = datetime.now(UTC)
    limit = int(os.getenv("MONTHLY_OPERATIONAL_CALL_LIMIT", str(MONTHLY_OPERATIONAL_CALL_LIMIT)))
    counter = _counter()
    budget = None
    if counter is not None:
        try:
            status = budget_status(counter.read(now), limit, now)
        except Exception:  # fail open: the operational limit is already half of the Free plan quota
            logger.warning("call_counter_unavailable", exc_info=True)
            status = None
        if status is not None:
            budget = status.as_dict()
            if not status.allows(calls) and event.get("skip_budget_check") is not True:
                log_event(logger, logging.WARNING, "collection_jobs_skipped", calls=calls, budget=budget, outcome="monthly_call_limit")
                emit_metrics({"CollectionJobsSkipped": calls})
                return {
                    "planned_jobs": 0,
                    "planned_calls": 0,
                    "skipped_calls": calls,
                    "reason": "monthly_call_limit",
                    "budget": budget,
                    "snapshot_at": snapshot_at,
                }

    enqueued = enqueue_jobs(queue_url, jobs)
    if counter is not None:
        try:
            counter.add(now, calls)
        except Exception:
            logger.warning("call_counter_update_failed", exc_info=True)
    log_event(
        logger,
        logging.INFO,
        "collection_jobs_planned",
        aws_request_id=getattr(context, "aws_request_id", None),
        jobs=enqueued,
        calls=calls,
        products=[job["product"] for job in jobs],
        budget=budget,
        processing_time_ms=round((time.perf_counter() - started) * 1000),
        outcome="planned",
    )
    emit_metrics({"CollectionJobsPlanned": calls})
    return {"planned_jobs": enqueued, "planned_calls": calls, "skipped_calls": 0, "snapshot_at": snapshot_at, "budget": budget}
