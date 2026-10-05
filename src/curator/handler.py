from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import boto3

from shared.capitals import BRAZIL_CAPITALS
from shared.daily_table import (
    aggregate_daily,
    build_curated_daily_key,
    daily_records_to_parquet,
    local_day_is_closed,
    utc_hours_for_local_date,
)
from shared.forecast_table import build_curated_forecast_key, build_forecast_records, forecast_records_to_parquet
from shared.hourly_table import (
    aggregate_hourly,
    build_curated_hourly_key,
    build_raw_hour_prefix,
    normalize_hourly_record,
    parse_target_hour,
    records_to_parquet,
)
from shared.observations import extract_air_pollution, extract_air_pollution_forecast, extract_current_weather, extract_forecast
from shared.parquet_io import PARQUET_CONTENT_TYPE, parquet_to_records
from shared.s3_io import list_keys, object_exists, parallel_map, put_bytes, put_json, read_bytes, read_json
from shared.serving import (
    SERIES_CACHE_CONTROL,
    build_daily_payload,
    build_forecast_payload,
    build_hourly_payload,
    daily_key,
    daily_rows,
    forecast_key,
    hourly_key,
    merge_daily_rows,
)
from shared.storage import find_latest_raw_keys, latest_keys_by_state
from shared.structured_logging import emit_metrics, log_event
from shared.time_utils import floor_hour, floor_minute, hour_range, iso_z

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DAILY_PREFIX = "curated/daily_observations/"
_DAILY_KEY_DATE = re.compile(r"weather_daily_observations_(\d{8})\.parquet$")

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


@dataclass(frozen=True)
class CuratorConfig:
    raw_bucket: str
    site_bucket: str | None = None
    lookback_hours: int = 6
    daily_lookback_days: int = 3
    serving_hourly_days: int = 7
    serving_daily_days: int = 730
    forecast_lookback_hours: int = 6
    air_forecast_lookback_hours: int = 12
    max_range_hours: int = 24 * 31
    max_workers: int = 16

    @classmethod
    def from_env(cls) -> CuratorConfig:
        raw_bucket = os.getenv("RAW_DATA_BUCKET_NAME", "")
        if not raw_bucket:
            raise RuntimeError("RAW_DATA_BUCKET_NAME is not configured")
        return cls(
            raw_bucket=raw_bucket,
            site_bucket=os.getenv("SITE_BUCKET_NAME") or None,
            lookback_hours=int(os.getenv("CURATOR_LOOKBACK_HOURS", "6")),
            daily_lookback_days=int(os.getenv("DAILY_LOOKBACK_DAYS", "3")),
            serving_hourly_days=int(os.getenv("SERVING_HOURLY_DAYS", "7")),
            serving_daily_days=int(os.getenv("SERVING_DAILY_DAYS", "730")),
        )


def _read_json_objects(s3_client: Any, bucket: str, keys: list[str], max_workers: int) -> list[dict[str, Any]]:
    bodies = parallel_map(lambda key: read_bytes(s3_client, bucket, key), keys, max_workers)
    return [json.loads(body.decode("utf-8")) for body in bodies if body is not None]


def _read_parquet_objects(s3_client: Any, bucket: str, keys: list[str], max_workers: int) -> list[dict[str, Any]]:
    bodies = parallel_map(lambda key: read_bytes(s3_client, bucket, key), keys, max_workers)
    return [normalize_hourly_record(row) for body in bodies if body is not None for row in parquet_to_records(body)]


def _extract_all(objects: list[dict[str, Any]], extractor: Any) -> list[dict[str, Any]]:
    return [item for source_object in objects if (item := extractor(source_object)) is not None]


def curate_hour(s3_client: Any, config: CuratorConfig, hour: datetime, force: bool = False, processed_at: datetime | None = None) -> dict[str, Any]:
    """Build the hourly observation table (weather + air quality) and the forecast table issued in `hour`."""
    hour = floor_hour(hour)
    processed_at = processed_at or floor_minute(datetime.now(UTC))
    bucket = config.raw_bucket
    result: dict[str, Any] = {
        "target_hour": iso_z(hour),
        "raw_prefix": build_raw_hour_prefix(hour),
        "curated_key": build_curated_hourly_key(hour),
        "forecast_key": build_curated_forecast_key(hour),
        "hourly": "skipped_existing",
        "forecast": "skipped_existing",
        "raw_objects": 0,
        "samples": 0,
        "records": 0,
        "forecast_records": 0,
        "local_dates": [],
    }

    if force or not object_exists(s3_client, bucket, result["curated_key"]):
        weather_objects = _read_json_objects(s3_client, bucket, list_keys(s3_client, bucket, build_raw_hour_prefix(hour)), config.max_workers)
        air_objects = _read_json_objects(s3_client, bucket, list_keys(s3_client, bucket, build_raw_hour_prefix(hour, "air_pollution")), config.max_workers)
        weather = _extract_all(weather_objects, extract_current_weather)
        air = _extract_all(air_objects, extract_air_pollution)
        records = aggregate_hourly(weather, air, processed_at)
        result.update({"raw_objects": len(weather_objects) + len(air_objects), "samples": len(weather), "air_samples": len(air)})
        if records:
            put_bytes(s3_client, bucket, result["curated_key"], records_to_parquet(records), PARQUET_CONTENT_TYPE)
            result.update({"hourly": "written", "records": len(records), "local_dates": sorted({record["local_date"] for record in records})})
        else:
            result["hourly"] = "no_data"

    if force or not object_exists(s3_client, bucket, result["forecast_key"]):
        forecast_keys = list(latest_keys_by_state(list_keys(s3_client, bucket, build_raw_hour_prefix(hour, "forecast_5d_3h"))).values())
        extracts = _extract_all(_read_json_objects(s3_client, bucket, forecast_keys, config.max_workers), extract_forecast)
        forecast_records = build_forecast_records(extracts, processed_at)
        if forecast_records:
            put_bytes(s3_client, bucket, result["forecast_key"], forecast_records_to_parquet(forecast_records), PARQUET_CONTENT_TYPE)
            result.update({"forecast": "written", "forecast_records": len(forecast_records)})
        else:
            result["forecast"] = "no_data"
    return result


def curate_daily(s3_client: Any, config: CuratorConfig, local_date: date, processed_at: datetime | None = None) -> dict[str, Any]:
    keys = [build_curated_hourly_key(hour) for hour in utc_hours_for_local_date(local_date)]
    hourly_records = _read_parquet_objects(s3_client, config.raw_bucket, keys, config.max_workers)
    records = aggregate_daily(hourly_records, local_date, processed_at)
    key = build_curated_daily_key(local_date)
    if not records:
        return {"date": local_date.isoformat(), "status": "no_data", "key": key, "records": []}
    put_bytes(s3_client, config.raw_bucket, key, daily_records_to_parquet(records), PARQUET_CONTENT_TYPE)
    return {"date": local_date.isoformat(), "status": "written", "key": key, "records": records}


def publish_hourly_series(s3_client: Any, config: CuratorConfig, now: datetime) -> int:
    end = parse_target_hour(None, now)
    start = end - timedelta(hours=config.serving_hourly_days * 24 - 1)
    keys = [build_curated_hourly_key(hour) for hour in hour_range(start, end)]
    by_state: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in _read_parquet_objects(s3_client, config.raw_bucket, keys, config.max_workers):
        by_state[str(record["state"])].append(record)
    site = str(config.site_bucket)
    parallel_map(
        lambda capital: put_json(
            s3_client,
            site,
            hourly_key(capital["state"]),
            build_hourly_payload(capital, by_state.get(capital["state"], []), now, config.serving_hourly_days),
            SERIES_CACHE_CONTROL,
        ),
        BRAZIL_CAPITALS,
        config.max_workers,
    )
    return len(BRAZIL_CAPITALS)


def _daily_keys_within(s3_client: Any, config: CuratorConfig, now: datetime) -> list[str]:
    oldest = (now - timedelta(days=config.serving_daily_days + 1)).strftime("%Y%m%d")
    keys: list[str] = []
    for key in list_keys(s3_client, config.raw_bucket, DAILY_PREFIX):
        match = _DAILY_KEY_DATE.search(key)
        if match and match.group(1) >= oldest:
            keys.append(key)
    return keys


def publish_daily_series(s3_client: Any, config: CuratorConfig, now: datetime, updated_records: list[dict[str, Any]], rebuild: bool = False) -> int:
    site = str(config.site_bucket)
    existing = dict(
        zip(
            [capital["state"] for capital in BRAZIL_CAPITALS],
            parallel_map(lambda capital: read_json(s3_client, site, daily_key(capital["state"])), BRAZIL_CAPITALS, config.max_workers),
            strict=True,
        )
    )
    rebuild = rebuild or any(document is None for document in existing.values())
    if rebuild:
        keys = _daily_keys_within(s3_client, config, now)
        bodies = parallel_map(lambda key: read_bytes(s3_client, config.raw_bucket, key), keys, config.max_workers)
        source_records = [row for body in bodies if body is not None for row in parquet_to_records(body)]
    elif updated_records:
        source_records = updated_records
    else:
        return 0

    updates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in source_records:
        updates[str(record["state"])].extend(daily_rows([record]))

    def write(capital: Any) -> None:
        state = capital["state"]
        previous_rows = [] if rebuild else (existing.get(state) or {}).get("rows", [])
        rows = merge_daily_rows(previous_rows, updates.get(state, []), config.serving_daily_days)
        put_json(s3_client, site, daily_key(state), build_daily_payload(capital, rows, now, config.serving_daily_days), SERIES_CACHE_CONTROL)

    capitals = BRAZIL_CAPITALS if rebuild else [capital for capital in BRAZIL_CAPITALS if capital["state"] in updates]
    parallel_map(write, capitals, config.max_workers)
    return len(capitals)


def publish_forecasts(s3_client: Any, config: CuratorConfig, now: datetime) -> int:
    bucket = config.raw_bucket
    expected = len(BRAZIL_CAPITALS)
    weather_keys = find_latest_raw_keys(s3_client, bucket, "forecast_5d_3h", now, config.forecast_lookback_hours, expected)
    air_keys = find_latest_raw_keys(s3_client, bucket, "air_pollution_forecast", now, config.air_forecast_lookback_hours, expected)
    weather = {
        item["state"]: item for item in _extract_all(_read_json_objects(s3_client, bucket, list(weather_keys.values()), config.max_workers), extract_forecast)
    }
    air = {
        item["state"]: item
        for item in _extract_all(_read_json_objects(s3_client, bucket, list(air_keys.values()), config.max_workers), extract_air_pollution_forecast)
    }
    site = str(config.site_bucket)

    def write(capital: Any) -> bool:
        state = capital["state"]
        if state not in weather and state not in air:
            return False  # keep whatever was published before
        payload = build_forecast_payload(capital, weather.get(state), air.get(state), now)
        if payload["weather"] is None or payload["air"] is None:
            previous = read_json(s3_client, site, forecast_key(state)) or {}
            payload["weather"] = payload["weather"] or previous.get("weather")
            payload["air"] = payload["air"] or previous.get("air")
        put_json(s3_client, site, forecast_key(state), payload, SERIES_CACHE_CONTROL)
        return True

    return sum(parallel_map(write, BRAZIL_CAPITALS, config.max_workers))


def _hours_for_event(event: dict[str, Any], config: CuratorConfig, now: datetime) -> tuple[list[datetime], bool]:
    force = event.get("force")
    if event.get("target_hour"):
        return [parse_target_hour(event["target_hour"])], True if force is None else bool(force)
    if event.get("start_hour") or event.get("end_hour"):
        last_closed = parse_target_hour(None, now)
        start = parse_target_hour(event.get("start_hour") or event.get("end_hour"))
        end = parse_target_hour(event["end_hour"]) if event.get("end_hour") else last_closed
        if end < start:
            raise ValueError("end_hour must not be before start_hour")
        hours = hour_range(start, end)
        if len(hours) > config.max_range_hours:
            raise ValueError(f"range has {len(hours)} hours; split it into chunks of at most {config.max_range_hours}")
        return hours, True if force is None else bool(force)
    last_closed = parse_target_hour(None, now)
    lookback = max(int(event.get("lookback_hours") or config.lookback_hours), 1)
    return hour_range(last_closed - timedelta(hours=lookback - 1), last_closed), bool(force)


def run(event: dict[str, Any], s3_client: Any, config: CuratorConfig, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    processed_at = floor_minute(now)
    hours, force = _hours_for_event(event, config, now)
    hour_results = [curate_hour(s3_client, config, hour, force, processed_at) for hour in hours]

    touched_dates = {local_date for result in hour_results for local_date in result["local_dates"]}
    newest_local_date = (now - timedelta(hours=5)).date()
    candidate_dates = touched_dates | {newest_local_date - timedelta(days=offset) for offset in range(1, config.daily_lookback_days + 1)}
    daily_results: list[dict[str, Any]] = []
    for local_date in sorted(candidate_dates):
        if not local_day_is_closed(local_date, now):
            continue
        if local_date in touched_dates or event.get("force_daily") or not object_exists(s3_client, config.raw_bucket, build_curated_daily_key(local_date)):
            daily_results.append(curate_daily(s3_client, config, local_date, processed_at))

    published: dict[str, int] = {}
    if config.site_bucket and event.get("publish", True):
        updated_daily = [record for result in daily_results for record in result["records"]]
        published = {
            "hourly": publish_hourly_series(s3_client, config, now),
            "daily": publish_daily_series(s3_client, config, now, updated_daily, bool(event.get("rebuild_serving"))),
            "forecast": publish_forecasts(s3_client, config, now),
        }

    return {
        "hours": [{key: value for key, value in result.items() if key != "local_dates"} for result in hour_results],
        "hours_written": sum(1 for result in hour_results if result["hourly"] == "written"),
        "forecasts_written": sum(1 for result in hour_results if result["forecast"] == "written"),
        "records": sum(result["records"] for result in hour_results),
        "daily": [{key: value for key, value in result.items() if key != "records"} | {"records": len(result["records"])} for result in daily_results],
        "published": published,
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    started = time.perf_counter()
    result = run(event or {}, _get_s3_client(), CuratorConfig.from_env())
    log_event(
        logger,
        logging.INFO,
        "curation_completed",
        aws_request_id=getattr(context, "aws_request_id", None),
        hours_written=result["hours_written"],
        forecasts_written=result["forecasts_written"],
        records=result["records"],
        daily=[item["date"] for item in result["daily"] if item["status"] == "written"],
        published=result["published"],
        processing_time_ms=round((time.perf_counter() - started) * 1000),
        outcome="curated",
    )
    emit_metrics({"HourlyObservationRecords": result["records"], "CuratedHours": result["hours_written"]})
    return result
