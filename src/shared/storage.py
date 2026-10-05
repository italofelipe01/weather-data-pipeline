from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError

from shared.s3_io import list_keys
from shared.time_utils import floor_hour, parse_utc

SAFE_COMPONENT = re.compile(r"[^a-z0-9._=-]+")
RAW_ROOT = "raw/source=openweather-free-plan"
_STATE_IN_KEY = re.compile(r"/state=([a-z0-9-]+)/")


def sanitize_component(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "-")
    normalized = SAFE_COMPONENT.sub("-", normalized)
    normalized = re.sub("-+", "-", normalized).strip("-._")
    return normalized or "unknown"


def build_raw_hour_prefix(product: str, hour: datetime) -> str:
    hour = floor_hour(hour)
    return f"{RAW_ROOT}/product={sanitize_component(product)}/year={hour:%Y}/month={hour:%m}/day={hour:%d}/hour={hour:%H}/"


def build_source_key(job: dict[str, Any]) -> str:
    snapshot = parse_utc(job["snapshot_at"])
    state = sanitize_component(str(job["state"]))
    city = sanitize_component(str(job["city"]))
    product = sanitize_component(str(job["product"]))
    timestamp = snapshot.strftime("%Y%m%dT%H%MZ")
    return f"{build_raw_hour_prefix(product, snapshot)}state={state}/city={city}/openweather_{product}_{state}_{city}_{timestamp}.json"


def state_from_key(key: str) -> str | None:
    match = _STATE_IN_KEY.search(key)
    return match.group(1).upper() if match else None


def latest_keys_by_state(keys: list[str]) -> dict[str, str]:
    """Pick the most recent raw key per UF. Keys end with a sortable UTC timestamp."""
    latest: dict[str, str] = {}
    for key in keys:
        state = state_from_key(key)
        if state and (state not in latest or key > latest[state]):
            latest[state] = key
    return latest


def find_latest_raw_keys(s3_client: Any, bucket: str, product: str, now: datetime, lookback_hours: int, expected_states: int | None = None) -> dict[str, str]:
    """Look back hour by hour (newest first) and keep the most recent snapshot found for each UF."""
    found: dict[str, str] = {}
    current = floor_hour(now)
    for offset in range(max(lookback_hours, 0) + 1):
        hour_keys = list_keys(s3_client, bucket, build_raw_hour_prefix(product, current - timedelta(hours=offset)))
        for state, key in latest_keys_by_state(hour_keys).items():
            found.setdefault(state, key)
        if expected_states is not None and len(found) >= expected_states:
            break
    return found


def build_source_object(job: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    canonical_response = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "source": "openweather-free-plan",
        "source_terms": "OpenWeather Free plan: 60 calls/minute and 1,000,000 calls/month.",
        "source_url": "https://openweathermap.org/price",
        "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "job": job,
        "response_hash": hashlib.sha256(canonical_response.encode("utf-8")).hexdigest(),
        "response": response,
    }


def put_json_once(s3_client: Any, bucket: str, key: str, payload: dict[str, Any]) -> str:
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
            IfNoneMatch="*",
        )
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = exc.response.get("Error", {}).get("Code")
        if status == 412 or code in {"PreconditionFailed", "412"}:
            return "duplicate"
        raise
    return "stored"
