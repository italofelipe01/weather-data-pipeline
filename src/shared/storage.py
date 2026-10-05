from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

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
    """Legacy per-capital key (objects written before batch collection; still readable)."""
    snapshot = parse_utc(job["snapshot_at"])
    state = sanitize_component(str(job["state"]))
    city = sanitize_component(str(job["city"]))
    product = sanitize_component(str(job["product"]))
    timestamp = snapshot.strftime("%Y%m%dT%H%MZ")
    return f"{build_raw_hour_prefix(product, snapshot)}state={state}/city={city}/openweather_{product}_{state}_{city}_{timestamp}.json"


def state_from_key(key: str) -> str | None:
    match = _STATE_IN_KEY.search(key)
    return match.group(1).upper() if match else None


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
