"""Read raw snapshots in both layouts: batch objects (one per product snapshot, all capitals) and the
legacy per-capital objects still present in raw/ until they expire."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from shared.collection import BATCH_FORMAT
from shared.s3_io import list_keys, parallel_map, read_bytes
from shared.storage import build_raw_hour_prefix, state_from_key
from shared.time_utils import floor_hour

_KEY_TIMESTAMP = re.compile(r"_(\d{8}T\d{4}Z)(?:_[0-9a-f]+)?\.json$")

Extractor = Callable[[dict[str, Any]], dict[str, Any] | None]


def expand_raw_object(raw_object: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-capital source objects ({"job", "response"}) from either layout."""
    if raw_object.get("format") == BATCH_FORMAT:
        return [
            {"source": raw_object.get("source"), "job": item.get("job"), "response": item.get("response"), "retrieved_at": item.get("retrieved_at")}
            for item in raw_object.get("items", [])
            if isinstance(item, dict)
        ]
    return [raw_object]


def key_timestamp(key: str) -> str:
    match = _KEY_TIMESTAMP.search(key)
    return match.group(1) if match else ""


def _load(s3_client: Any, bucket: str, key: str) -> list[dict[str, Any]]:
    body = read_bytes(s3_client, bucket, key)
    return expand_raw_object(json.loads(body.decode("utf-8"))) if body is not None else []


def read_hour(s3_client: Any, bucket: str, product: str, hour: datetime, extractor: Extractor, max_workers: int = 16) -> tuple[int, list[dict[str, Any]]]:
    """Every snapshot of `product` collected in `hour`, extracted. Returns (objects read, extracted items)."""
    keys = list_keys(s3_client, bucket, build_raw_hour_prefix(product, hour))
    loaded = parallel_map(lambda key: _load(s3_client, bucket, key), keys, max_workers)
    items = [item for sources in loaded for source in sources if (item := extractor(source)) is not None]
    return len(keys), items


def latest_by_state(
    s3_client: Any,
    bucket: str,
    product: str,
    now: datetime,
    lookback_hours: int,
    extractor: Extractor,
    expected_states: int = 27,
) -> dict[str, dict[str, Any]]:
    """Most recent extracted snapshot per UF, walking hour prefixes newest first and reading as little as possible."""
    found: dict[str, dict[str, Any]] = {}
    current = floor_hour(now)
    for offset in range(max(lookback_hours, 0) + 1):
        keys = list_keys(s3_client, bucket, build_raw_hour_prefix(product, current - timedelta(hours=offset)))
        for key in sorted(keys, key=key_timestamp, reverse=True):
            state = state_from_key(key)
            if state is not None and state in found:
                continue  # legacy per-capital object for a UF we already have
            for source in _load(s3_client, bucket, key):
                item = extractor(source)
                if item is not None:
                    found.setdefault(item["state"], item)
            if len(found) >= expected_states:
                return found
    return found
