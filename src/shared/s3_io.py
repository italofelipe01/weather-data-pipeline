from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from botocore.exceptions import ClientError

_MISSING_CODES = {"NoSuchKey", "404", "NotFound"}


def is_missing(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in _MISSING_CODES or status == 404


def list_keys(s3_client: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    continuation_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        response = s3_client.list_objects_v2(**kwargs)
        keys.extend(item["Key"] for item in response.get("Contents", []))
        if not response.get("IsTruncated"):
            return keys
        continuation_token = response.get("NextContinuationToken")


def read_bytes(s3_client: Any, bucket: str, key: str) -> bytes | None:
    try:
        return s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as exc:
        if is_missing(exc):
            return None
        raise


def read_json(s3_client: Any, bucket: str, key: str) -> Any | None:
    body = read_bytes(s3_client, bucket, key)
    if body is None:
        return None
    return json.loads(body.decode("utf-8"))


def object_exists(s3_client: Any, bucket: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if is_missing(exc):
            return False
        raise
    return True


def put_bytes(s3_client: Any, bucket: str, key: str, body: bytes, content_type: str, cache_control: str | None = None) -> None:
    kwargs: dict[str, Any] = {
        "Bucket": bucket,
        "Key": key,
        "Body": body,
        "ContentType": content_type,
        "ServerSideEncryption": "AES256",
    }
    if cache_control:
        kwargs["CacheControl"] = cache_control
    s3_client.put_object(**kwargs)


def put_json(s3_client: Any, bucket: str, key: str, payload: Any, cache_control: str | None = "public, max-age=60") -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    put_bytes(s3_client, bucket, key, body, "application/json; charset=utf-8", cache_control)


def parallel_map[T, R](func: Callable[[T], R], items: Iterable[T], max_workers: int = 16) -> list[R]:
    """Map preserving order. boto3 clients are thread-safe, so S3 reads can fan out."""
    values = list(items)
    if len(values) <= 1 or max_workers <= 1:
        return [func(item) for item in values]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(values))) as executor:
        return list(executor.map(func, values))
