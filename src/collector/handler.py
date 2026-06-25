from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.openweather import SourceError, fetch_free_plan_weather
from shared.secrets import get_openweather_api_key
from shared.storage import build_source_key, build_source_object, put_json_once
from shared.structured_logging import log_count_metric, log_event

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


def process_job(job: dict[str, Any]) -> tuple[str, str]:
    bucket = os.getenv("RAW_DATA_BUCKET_NAME", "")
    if not bucket:
        raise RuntimeError("RAW_DATA_BUCKET_NAME is not configured")
    parameter_name = os.getenv("OPENWEATHER_API_KEY_PARAMETER_NAME", "")
    if not parameter_name:
        raise RuntimeError("OPENWEATHER_API_KEY_PARAMETER_NAME is not configured")
    api_key = get_openweather_api_key(_get_ssm_client(), parameter_name)
    response = fetch_free_plan_weather(job, api_key, timeout_seconds=int(os.getenv("SOURCE_TIMEOUT_SECONDS", "30")))
    key = build_source_key(job)
    outcome = put_json_once(_get_s3_client(), bucket, key, build_source_object(job, response))
    return key, outcome


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        started = time.perf_counter()
        message_id = record.get("messageId", "unknown")
        try:
            job = json.loads(record.get("body", "{}"))
            key, outcome = process_job(job)
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
            log_count_metric(logger, "SourceJobsCollected", state=job.get("state"))
        except SourceError as exc:
            if not exc.retryable:
                log_event(logger, logging.ERROR, "source_job_rejected", correlation_id=message_id, outcome="not_retryable")
                continue
            failures.append({"itemIdentifier": message_id})
            log_event(logger, logging.ERROR, "source_job_failed", correlation_id=message_id, outcome="retry")
            log_count_metric(logger, "SourceJobFailures", correlation_id=message_id)
            logger.exception("collector_record_error")
        except ClientError:
            failures.append({"itemIdentifier": message_id})
            log_event(logger, logging.ERROR, "source_job_failed", correlation_id=message_id, outcome="retry")
            log_count_metric(logger, "SourceJobFailures", correlation_id=message_id)
            logger.exception("collector_record_error")
        except Exception:
            failures.append({"itemIdentifier": message_id})
            log_event(logger, logging.ERROR, "source_job_failed", correlation_id=message_id, outcome="retry")
            log_count_metric(logger, "SourceJobFailures", correlation_id=message_id)
            logger.exception("collector_record_error")
    return {"batchItemFailures": failures}
