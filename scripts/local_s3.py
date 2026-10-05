"""Filesystem-backed stand-in for the S3 client calls used by the pipeline (local runs and previews)."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError


def _error(code: str, status: int, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, operation)


class LocalDirS3:
    def __init__(self, buckets: dict[str, Path]) -> None:
        self.buckets = {name: Path(path).resolve() for name, path in buckets.items()}

    def _root(self, bucket: str) -> Path:
        if bucket not in self.buckets:
            raise _error("NoSuchBucket", 404, "Bucket")
        return self.buckets[bucket]

    def _path(self, bucket: str, key: str) -> Path:
        root = self._root(bucket)
        path = (root / key).resolve()
        if not path.is_relative_to(root):
            raise _error("InvalidKey", 400, "Key")
        return path

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        path = self._path(kwargs["Bucket"], kwargs["Key"])
        if kwargs.get("IfNoneMatch") == "*" and path.exists():
            raise _error("PreconditionFailed", 412, "PutObject")
        path.parent.mkdir(parents=True, exist_ok=True)
        body = kwargs["Body"]
        path.write_bytes(body if isinstance(body, bytes) else str(body).encode("utf-8"))
        return {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        path = self._path(kwargs["Bucket"], kwargs["Key"])
        if not path.is_file():
            raise _error("NoSuchKey", 404, "GetObject")
        return {"Body": io.BytesIO(path.read_bytes())}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        if not self._path(kwargs["Bucket"], kwargs["Key"]).is_file():
            raise _error("404", 404, "HeadObject")
        return {}

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        root = self._root(kwargs["Bucket"])
        prefix = kwargs.get("Prefix", "")
        base = root / (prefix if prefix.endswith("/") else os.path.dirname(prefix))
        keys: list[str] = []
        if base.is_dir():
            for directory, _, files in os.walk(base):
                for name in files:
                    key = (Path(directory) / name).relative_to(root).as_posix()
                    if key.startswith(prefix):
                        keys.append(key)
        keys.sort()
        start = int(kwargs.get("ContinuationToken") or 0)
        page = keys[start : start + 1000]
        response: dict[str, Any] = {"Contents": [{"Key": key} for key in page], "IsTruncated": start + 1000 < len(keys)}
        if response["IsTruncated"]:
            response["NextContinuationToken"] = str(start + 1000)
        return response
