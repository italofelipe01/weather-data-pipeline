from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

SAFE_COMPONENT = re.compile(r"[^a-z0-9._=-]+")


def sanitize_component(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "-")
    normalized = SAFE_COMPONENT.sub("-", normalized)
    normalized = re.sub("-+", "-", normalized).strip("-._")
    return normalized or "unknown"


def build_source_key(job: dict[str, Any]) -> str:
    snapshot = datetime.fromisoformat(str(job["snapshot_at"]).replace("Z", "+00:00")).astimezone(UTC)
    state = sanitize_component(str(job["state"]))
    city = sanitize_component(str(job["city"]))
    product = sanitize_component(str(job["product"]))
    timestamp = snapshot.strftime("%Y%m%dT%H%MZ")
    return (
        f"raw/source=openweather-free-plan/product={product}/year={snapshot:%Y}/month={snapshot:%m}/day={snapshot:%d}/hour={snapshot:%H}/"
        f"state={state}/city={city}/"
        f"openweather_{product}_{state}_{city}_{timestamp}.json"
    )


def build_source_object(job: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    canonical_response = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "source": "openweather-free-plan",
        "source_terms": "OpenWeather Free plan: 60 calls/minute and 1,000,000 calls/month for current weather and forecasts.",
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
