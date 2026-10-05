import json
from datetime import UTC, date, datetime

import pytest
from botocore.exceptions import ClientError

from curator.handler import CuratorConfig, run
from publisher.handler import PublisherConfig, publish_latest
from scripts import sample_data
from scripts.local_s3 import LocalDirS3


def test_local_dir_s3_behaves_like_the_s3_subset(tmp_path) -> None:
    s3 = LocalDirS3({"b": tmp_path / "bucket"})
    s3.put_object(Bucket="b", Key="raw/a/1.json", Body=b"{}", IfNoneMatch="*")
    s3.put_object(Bucket="b", Key="raw/a/2.json", Body="{}")
    s3.put_object(Bucket="b", Key="raw/b.json", Body=b"{}")
    with pytest.raises(ClientError) as duplicate:
        s3.put_object(Bucket="b", Key="raw/a/1.json", Body=b"{}", IfNoneMatch="*")
    assert duplicate.value.response["ResponseMetadata"]["HTTPStatusCode"] == 412
    assert [item["Key"] for item in s3.list_objects_v2(Bucket="b", Prefix="raw/a/")["Contents"]] == ["raw/a/1.json", "raw/a/2.json"]
    assert [item["Key"] for item in s3.list_objects_v2(Bucket="b", Prefix="raw/")["Contents"]] == ["raw/a/1.json", "raw/a/2.json", "raw/b.json"]
    assert s3.list_objects_v2(Bucket="b", Prefix="missing/")["Contents"] == []
    assert s3.get_object(Bucket="b", Key="raw/b.json")["Body"].read() == b"{}"
    s3.head_object(Bucket="b", Key="raw/b.json")
    for call in (s3.get_object, s3.head_object):
        with pytest.raises(ClientError):
            call(Bucket="b", Key="nope.json")
    with pytest.raises(ClientError):
        s3.put_object(Bucket="b", Key="../escape.json", Body=b"x")
    with pytest.raises(ClientError):
        s3.list_objects_v2(Bucket="unknown", Prefix="")


def test_synthetic_data_runs_through_curator_and_publisher(tmp_path) -> None:
    s3 = LocalDirS3({sample_data.RAW_BUCKET: tmp_path / "raw", sample_data.SITE_BUCKET: tmp_path / "site"})
    now = datetime(2026, 7, 15, 7, 25, tzinfo=UTC)
    assert sample_data.generate_raw(s3, now, hours=3) > 0
    assert sample_data.generate_daily_history(s3, date(2026, 7, 10), date(2026, 7, 13)) == 4

    curation = run({"rebuild_serving": True}, s3, CuratorConfig(raw_bucket=sample_data.RAW_BUCKET, site_bucket=sample_data.SITE_BUCKET, lookback_hours=3), now)
    assert curation["hours_written"] == 3
    assert curation["forecasts_written"] == 3
    assert curation["published"] == {"hourly": 27, "daily": 27, "forecast": 27}

    latest = publish_latest(s3, PublisherConfig(raw_bucket=sample_data.RAW_BUCKET, site_bucket=sample_data.SITE_BUCKET), now)
    assert latest["current_capitals"] == 27
    assert latest["air_capitals"] == 27

    site = tmp_path / "site" / "data"
    payload = json.loads((site / "latest.json").read_text(encoding="utf-8"))
    assert all(item["current"] and item["air"] for item in payload["capitals"])
    daily = json.loads((site / "daily" / "rs.json").read_text(encoding="utf-8"))
    assert [row["observation_date"] for row in daily["rows"]][:4] == ["2026-07-10", "2026-07-11", "2026-07-12", "2026-07-13"]
    forecast = json.loads((site / "forecast" / "am.json").read_text(encoding="utf-8"))
    assert len(forecast["weather"]["items"]) == 40
    assert len(forecast["air"]["items"]) == 96


def test_local_pipeline_collects_with_spacing_and_reprocesses(tmp_path, monkeypatch) -> None:
    from scripts import local_pipeline
    from shared.capitals import get_capitals
    from shared.openweather import SourceError
    from shared.source_plan import build_collection_jobs
    from tests.helpers import RESPONSE_BUILDERS

    def fake_fetch(job, api_key, timeout_seconds):
        if job["state"] == "RJ" and job["product"] == "air_pollution":
            raise SourceError("openweather returned HTTP 429", retryable=True, status_code=429)
        return RESPONSE_BUILDERS[job["product"]](str(job["snapshot_at"]))

    sleeps = []
    monkeypatch.setattr(local_pipeline, "fetch_free_plan_weather", fake_fetch)
    monkeypatch.setattr(local_pipeline.time, "sleep", sleeps.append)
    s3 = LocalDirS3({local_pipeline.RAW_BUCKET: tmp_path / "raw", local_pipeline.SITE_BUCKET: tmp_path / "site"})
    jobs = build_collection_jobs(get_capitals(["SP", "RJ"]), ["current_weather", "air_pollution"], "metric", "pt_br", "2026-07-15T12:03:00Z")
    stored, failures = local_pipeline.collect(s3, jobs, "key", min_interval=1.1, timeout=5)
    assert (stored, failures) == (3, 1)
    assert len(sleeps) == 3 and all(0 < value <= 1.1 for value in sleeps)

    monkeypatch.setattr(
        "sys.argv",
        ["local_pipeline.py", "--skip-fetch", "--raw-dir", str(tmp_path / "raw"), "--site-dir", str(tmp_path / "site")],
    )
    assert local_pipeline.main() == 0
    assert (tmp_path / "site" / "data" / "latest.json").exists()
