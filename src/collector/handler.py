from __future__ import annotations

import json
import logging
import os
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import boto3

from shared.collection import build_batch_key, collect_batch, is_expired
from shared.openweather import fetch_free_plan_weather
from shared.secrets import get_openweather_api_key, reset_api_key_cache
from shared.storage import put_json_once
from shared.structured_logging import emit_metrics, log_event

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


class BatchFailedError(RuntimeError):
    """Every capital failed with a retryable error: let SQS retry the whole snapshot."""


def process_batch(batch_job: dict[str, Any], context: Any = None, counters: Counter[str] | None = None) -> dict[str, Any]:
    counters = counters if counters is not None else Counter()
    bucket = os.getenv("RAW_DATA_BUCKET_NAME", "")
    if not bucket:
        raise RuntimeError("RAW_DATA_BUCKET_NAME is not configured")
    parameter_name = os.getenv("OPENWEATHER_API_KEY_PARAMETER_NAME", "")
    if not parameter_name:
        raise RuntimeError("OPENWEATHER_API_KEY_PARAMETER_NAME is not configured")
    capitals = len(batch_job.get("capitals", []))
    if is_expired(batch_job, datetime.now(UTC)):
        counters["SourceJobsExpired"] += capitals
        return {"outcome": "expired", "product": batch_job.get("product"), "snapshot_at": batch_job.get("snapshot_at")}

    timeout = int(os.getenv("SOURCE_TIMEOUT_SECONDS", "8"))
    remaining = (lambda: context.get_remaining_time_in_millis() / 1000) if hasattr(context, "get_remaining_time_in_millis") else None
    result = collect_batch(
        batch_job,
        lambda job: fetch_free_plan_weather(job, get_openweather_api_key(_get_ssm_client(), parameter_name), timeout_seconds=timeout),
        min_interval=float(os.getenv("SOURCE_MIN_INTERVAL_SECONDS", "1.1")),
        remaining_seconds=remaining,
        on_unauthorized=reset_api_key_cache,
    )
    counters["OpenWeatherApiCalls"] += result.calls
    counters["SourceJobsCollected"] += len(result.items)
    counters["SourceJobFailures"] += len(result.failures)
    counters["SourceJobsRejected"] += len(result.rejected)
    if not result.items:
        if result.failures:
            raise BatchFailedError(f"all {len(result.failures)} capitals failed: {result.failures[0]['error']}")
        return {"outcome": "rejected", "product": result.product, "snapshot_at": result.snapshot_at, "rejected": result.rejected}
    states = [str(capital.get("state")) for capital in batch_job.get("capitals", [])]
    key = build_batch_key(result.product, result.snapshot_at, states)
    outcome = put_json_once(_get_s3_client(), bucket, key, result.raw_object())
    return {
        "outcome": outcome,
        "product": result.product,
        "snapshot_at": result.snapshot_at,
        "s3_key": key,
        "collected": len(result.items),
        "failures": result.failures,
        "rejected": result.rejected,
        "calls": result.calls,
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    counters: Counter[str] = Counter(
        {"OpenWeatherApiCalls": 0, "SourceJobsCollected": 0, "SourceJobFailures": 0, "SourceJobsRejected": 0, "SourceJobsExpired": 0}
    )
    for record in (event or {}).get("Records", []):
        started = time.perf_counter()
        message_id = record.get("messageId", "unknown")
        try:
            batch_job = json.loads(record.get("body", "{}"))
        except json.JSONDecodeError:
            counters["SourceJobsRejected"] += 1
            log_event(logger, logging.ERROR, "source_batch_rejected", correlation_id=message_id, error="invalid message body", outcome="not_retryable")
            continue
        try:
            summary = process_batch(batch_job, context, counters)
        except Exception as exc:
            failures.append({"itemIdentifier": message_id})
            log_event(
                logger,
                logging.ERROR,
                "source_batch_failed",
                correlation_id=message_id,
                product=batch_job.get("product"),
                snapshot_at=batch_job.get("snapshot_at"),
                error=str(exc) if isinstance(exc, BatchFailedError) else type(exc).__name__,
                outcome="retry",
            )
            if not isinstance(exc, BatchFailedError):
                logger.exception("collector_batch_error")
            continue
        level = logging.WARNING if summary.get("failures") or summary.get("rejected") else logging.INFO
        log_event(
            logger,
            level,
            "source_batch_processed",
            correlation_id=message_id,
            aws_request_id=getattr(context, "aws_request_id", None),
            processing_time_ms=round((time.perf_counter() - started) * 1000),
            **summary,
        )
    emit_metrics(dict(counters))
    return {"batchItemFailures": failures}
