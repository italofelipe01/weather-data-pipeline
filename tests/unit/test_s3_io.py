import json

import pytest
from botocore.exceptions import ClientError

from shared.s3_io import list_keys, object_exists, parallel_map, put_json, read_bytes, read_json
from tests.helpers import MemoryS3


class DeniedS3:
    def get_object(self, **kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied"}, "ResponseMetadata": {"HTTPStatusCode": 403}}, "GetObject")

    def head_object(self, **kwargs):
        self.get_object()


def test_list_keys_follows_pagination() -> None:
    s3 = MemoryS3(page_size=2)
    for index in range(5):
        s3.put_object(Bucket="b", Key=f"p/{index}", Body=b"x")
    s3.put_object(Bucket="b", Key="other", Body=b"x")
    assert list_keys(s3, "b", "p/") == [f"p/{index}" for index in range(5)]
    assert s3.count("list_objects_v2") == 3


def test_missing_objects_are_none_or_false() -> None:
    s3 = MemoryS3()
    assert read_bytes(s3, "b", "missing") is None
    assert read_json(s3, "b", "missing") is None
    assert object_exists(s3, "b", "missing") is False


def test_access_errors_are_not_hidden() -> None:
    with pytest.raises(ClientError):
        read_bytes(DeniedS3(), "b", "k")
    with pytest.raises(ClientError):
        object_exists(DeniedS3(), "b", "k")


def test_put_json_sets_metadata_and_round_trips() -> None:
    s3 = MemoryS3()
    put_json(s3, "b", "data/x.json", {"city": "São Paulo"}, cache_control="no-cache")
    stored = s3.buckets["b"]["data/x.json"]
    assert stored["ContentType"].startswith("application/json")
    assert stored["CacheControl"] == "no-cache"
    assert stored["ServerSideEncryption"] == "AES256"
    assert read_json(s3, "b", "data/x.json") == {"city": "São Paulo"}
    assert object_exists(s3, "b", "data/x.json") is True
    assert "São Paulo" in s3.body("b", "data/x.json").decode("utf-8")
    with pytest.raises(ValueError):
        put_json(s3, "b", "nan.json", {"value": float("nan")})
    assert json.loads(s3.body("b", "data/x.json"))


def test_parallel_map_preserves_order() -> None:
    assert parallel_map(lambda value: value * 2, range(20), max_workers=4) == [value * 2 for value in range(20)]
    assert parallel_map(str, [1]) == ["1"]
