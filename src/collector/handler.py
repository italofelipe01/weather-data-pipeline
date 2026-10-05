from __future__ import annotations

import json
import logging
import os
import time
from collections import Counter
from typing import Any

import boto3

from shared.openweather import SourceError, fetch_free_plan_weather
from shared.secrets import get_openweather_api_key, reset_api_key_cache
from shared.storage import build_source_key, build_source_object, put_json_once
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


def process_job(job: dict[str, Any], counters: Counter[str] | None = None) -> tuple[str, str]:
    bucket = os.getenv("RAW_DATA_BUCKET_NAME", "")
    if not bucket:
        raise RuntimeError("RAW_DATA_BUCKET_NAME is not configured")
    parameter_name = os.getenv("OPENWEATHER_API_KEY_PARAMETER_NAME", "")
    if not parameter_name:
        raise RuntimeError("OPENWEATHER_API_KEY_PARAMETER_NAME is not configured")
    api_key = get_openweather_api_key(_get_ssm_client(), parameter_name)
    if counters is not None:
        # Every request counts against the OpenWeather quota, successful or not.
        counters["OpenWeatherApiCalls"] += 1
    try:
        response = fetch_free_plan_weather(job, api_key, timeout_seconds=int(os.getenv("SOURCE_TIMEOUT_SECONDS", "10")))
    except SourceError as exc:
        if exc.status_code == 401:
            reset_api_key_cache()
        raise
    key = build_source_key(job)
    outcome = put_json_once(_get_s3_client(), bucket, key, build_source_object(job, response))
    return key, outcome


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    counters: Counter[str] = Counter({"OpenWeatherApiCalls": 0, "SourceJobsCollected": 0, "SourceJobFailures": 0, "SourceJobsRejected": 0})
    for record in (event or {}).get("Records", []):
        started = time.perf_counter()
        message_id = record.get("messageId", "unknown")
        job: dict[str, Any] = {}
        try:
            job = json.loads(record.get("body", "{}"))
            key, outcome = process_job(job, counters)
            counters["SourceJobsCollected"] += 1
            log_event(
                logger,
                logging.INFO,
                "source_job_processed",
                correlation_id=message_id,
                city=job.get("city"),
                state=job.get("state"),
                product=job.get("product"),
                snapshot_at=job.get("snapshot_at"),
                s3_key=key,
                outcome=outcome,
                aws_request_id=getattr(context, "aws_request_id", None),
                processing_time_ms=round((time.perf_counter() - started) * 1000),
            )
        except json.JSONDecodeError:
            counters["SourceJobsRejected"] += 1
            log_event(logger, logging.ERROR, "source_job_rejected", correlation_id=message_id, error="invalid message body", outcome="not_retryable")
        except SourceError as exc:
            if not exc.retryable:
                counters["SourceJobsRejected"] += 1
                log_event(
                    logger,
                    logging.ERROR,
                    "source_job_rejected",
                    correlation_id=message_id,
                    state=job.get("state"),
                    product=job.get("product"),
                    error=str(exc),
                    status_code=exc.status_code,
                    outcome="not_retryable",
                )
                continue
            failures.append({"itemIdentifier": message_id})
            counters["SourceJobFailures"] += 1
            log_event(
                logger,
                logging.ERROR,
                "source_job_failed",
                correlation_id=message_id,
                state=job.get("state"),
                product=job.get("product"),
                error=str(exc),
                status_code=exc.status_code,
                outcome="retry",
            )
        except Exception as exc:
            failures.append({"itemIdentifier": message_id})
            counters["SourceJobFailures"] += 1
            log_event(
                logger,
                logging.ERROR,
                "source_job_failed",
                correlation_id=message_id,
                state=job.get("state"),
                product=job.get("product"),
                error=type(exc).__name__,
                outcome="retry",
            )
            logger.exception("collector_record_error")
    emit_metrics(dict(counters))
    return {"batchItemFailures": failures}
