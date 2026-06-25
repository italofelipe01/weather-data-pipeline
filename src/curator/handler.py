from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3

from shared.hourly_table import (
    aggregate_hourly,
    build_curated_hourly_key,
    build_raw_hour_prefix,
    extract_current_weather_sample,
    parse_target_hour,
    records_to_parquet,
)
from shared.structured_logging import log_count_metric, log_event

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _iter_raw_objects(s3_client: Any, bucket: str, prefix: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    continuation_token: str | None = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        response = s3_client.list_objects_v2(**kwargs)
        for item in response.get("Contents", []):
            key = item["Key"]
            body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
            objects.append(json.loads(body.decode("utf-8")))
        if not response.get("IsTruncated"):
            return objects
        continuation_token = response.get("NextContinuationToken")


def curate_hour(target_hour_value: object | None = None) -> dict[str, Any]:
    bucket = os.getenv("RAW_DATA_BUCKET_NAME", "")
    if not bucket:
        raise RuntimeError("RAW_DATA_BUCKET_NAME is not configured")

    target_hour = parse_target_hour(target_hour_value)
    raw_prefix = build_raw_hour_prefix(target_hour)
    curated_key = build_curated_hourly_key(target_hour)
    s3_client = _get_s3_client()
    raw_objects = _iter_raw_objects(s3_client, bucket, raw_prefix)
    samples = [sample for source_object in raw_objects if (sample := extract_current_weather_sample(source_object)) is not None]
    records = aggregate_hourly(samples)
    parquet_body = records_to_parquet(records)
    s3_client.put_object(
        Bucket=bucket,
        Key=curated_key,
        Body=parquet_body,
        ContentType="application/vnd.apache.parquet",
        ServerSideEncryption="AES256",
    )
    return {
        "target_hour": target_hour.isoformat().replace("+00:00", "Z"),
        "raw_prefix": raw_prefix,
        "curated_key": curated_key,
        "raw_objects": len(raw_objects),
        "samples": len(samples),
        "records": len(records),
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    started = time.perf_counter()
    result = curate_hour((event or {}).get("target_hour"))
    log_event(
        logger,
        logging.INFO,
        "hourly_observations_curated",
        aws_request_id=getattr(context, "aws_request_id", None),
        target_hour=result["target_hour"],
        raw_objects=result["raw_objects"],
        samples=result["samples"],
        records=result["records"],
        curated_key=result["curated_key"],
        processing_time_ms=round((time.perf_counter() - started) * 1000),
        outcome="curated",
    )
    log_count_metric(logger, "HourlyObservationRecords", records=result["records"])
    return result
