import json
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from scripts import offline_service
from scripts.offline_service import OfflinePipeline, Schedule, Settings, prune_raw, start_dashboard
from tests.helpers import RESPONSE_BUILDERS


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def _fake_fetch(calls: list[str]):
    def fetch(job, api_key, timeout_seconds):
        calls.append(f"{job['product']}:{job['state']}")
        return RESPONSE_BUILDERS[job["product"]](job["snapshot_at"])

    return fetch


def _pipeline(tmp_path, calls, **overrides) -> OfflinePipeline:
    settings = Settings(data_dir=tmp_path / "data", site_dir=tmp_path / "site", api_key="key", states=["SP", "RJ"], min_call_interval=0, **overrides)
    return OfflinePipeline(settings, fetch=_fake_fetch(calls), sleep=lambda seconds: None)


def test_schedules_match_the_cloud_cadence() -> None:
    now = _utc("2026-06-25T13:04:30")
    assert Schedule(every_minutes=3).previous_fire(now) == _utc("2026-06-25T13:03:00")
    assert Schedule(minute=5).previous_fire(now) == _utc("2026-06-25T12:05:00")
    assert Schedule(minute=5).previous_fire(_utc("2026-06-25T13:05:00")) == _utc("2026-06-25T13:05:00")
    assert Schedule(minute=50, every_hours=6).previous_fire(now) == _utc("2026-06-25T12:50:00")
    assert Schedule(minute=50, every_hours=6).previous_fire(_utc("2026-06-25T11:00:00")) == _utc("2026-06-25T06:50:00")
    assert Schedule(minute=40, every_hours=24).previous_fire(now) == _utc("2026-06-25T00:40:00")


def test_run_due_runs_missed_tasks_once_then_follows_the_schedule(tmp_path) -> None:
    calls: list[str] = []
    pipeline = _pipeline(tmp_path, calls)
    first = _utc("2026-06-25T13:04:00")
    ran = pipeline.run_due(first, clock=lambda: first)
    assert ran == [
        "collect:current_weather",
        "collect:forecast_5d_3h",
        "collect:air_pollution",
        "collect:air_pollution_forecast",
        "curate",
        "publish",
        "prune",
    ]
    assert len(calls) == 8
    assert pipeline.run_due(first, clock=lambda: first) == []

    later = first + timedelta(minutes=2)  # 13:06: current weather (13:06) and the 13:05 forecast are due
    assert pipeline.run_due(later, clock=lambda: later) == ["collect:current_weather", "collect:forecast_5d_3h"]
    hour_later = _utc("2026-06-25T14:21:00")
    assert pipeline.run_due(hour_later, clock=lambda: hour_later) == [
        "collect:current_weather",
        "collect:forecast_5d_3h",
        "collect:air_pollution",
        "curate",
        "publish",
    ]

    latest = json.loads((tmp_path / "site" / "data" / "latest.json").read_text(encoding="utf-8"))
    assert latest["runtime"] == "local"
    assert latest["budget"]["calls_month_to_date"] == len(calls)
    lake_objects = list((tmp_path / "data" / "lake" / "raw").rglob("*.json"))
    assert len(lake_objects) == 9  # one object per product snapshot, not one per capital
    assert (tmp_path / "site" / "data" / "forecast" / "sp.json").exists()


def test_monthly_limit_is_enforced_locally(tmp_path) -> None:
    calls: list[str] = []
    pipeline = _pipeline(tmp_path, calls, monthly_limit=3, air_pollution=False)
    now = _utc("2026-06-25T13:04:00")
    assert pipeline.collect("current_weather", now)["calls"] == 2
    assert pipeline.collect("forecast_5d_3h", now) == {"product": "forecast_5d_3h", "outcome": "monthly_call_limit"}
    assert len(calls) == 2
    assert [task.name for task in pipeline.tasks if task.name.startswith("collect:")] == ["collect:current_weather", "collect:forecast_5d_3h"]


def test_run_once_collects_everything_and_publishes(tmp_path) -> None:
    calls: list[str] = []
    pipeline = _pipeline(tmp_path, calls)
    names = pipeline.run_once(clock=lambda: _utc("2026-06-25T13:04:00"))
    assert names[-2:] == ["curate", "publish"]
    assert len(calls) == 8
    latest = json.loads((tmp_path / "site" / "data" / "latest.json").read_text(encoding="utf-8"))
    assert {item["state"] for item in latest["capitals"] if item["current"]} == {"SP", "RJ"}


def test_failed_task_does_not_stop_the_scheduler(tmp_path) -> None:
    def broken(job, api_key, timeout_seconds):
        raise RuntimeError("network down")

    settings = Settings(data_dir=tmp_path / "data", site_dir=tmp_path / "site", api_key="key", states=["SP"], min_call_interval=0)
    pipeline = OfflinePipeline(settings, fetch=broken)
    now = _utc("2026-06-25T13:04:00")
    assert "publish" in pipeline.run_due(now, clock=lambda: now)


def test_prune_raw_keeps_recent_partitions(tmp_path) -> None:
    lake = tmp_path / "lake"
    for day in ("01", "20", "25"):
        folder = lake / "raw" / "source=openweather-free-plan" / "product=current_weather" / "year=2026" / "month=06" / f"day={day}" / "hour=12"
        folder.mkdir(parents=True)
        (folder / "x.json").write_text("{}", encoding="utf-8")
    (lake / "curated" / "daily_observations").mkdir(parents=True)
    assert prune_raw(lake, 10, _utc("2026-06-25T12:00:00")) == 1
    assert sorted(path.name for path in (lake / "raw" / "source=openweather-free-plan" / "product=current_weather" / "year=2026" / "month=06").iterdir()) == [
        "day=20",
        "day=25",
    ]
    assert prune_raw(lake, 0, _utc("2026-06-25T12:00:00")) == 0
    assert (lake / "curated" / "daily_observations").exists()


def test_dashboard_server_serves_site_and_fresh_data(tmp_path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>ok</title>", encoding="utf-8")
    (tmp_path / "data" / "latest.json").write_text("{}", encoding="utf-8")
    server = start_dashboard(tmp_path, "127.0.0.1", 0)
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
            assert b"<title>ok</title>" in response.read()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/data/latest.json") as response:
            assert response.headers["Cache-Control"] == "no-cache"
    finally:
        server.shutdown()


def test_main_requires_an_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    code = offline_service.main(["--once", "--data-dir", str(tmp_path / "data"), "--env-file", str(tmp_path / "missing.env")])
    assert code == 2


def test_main_once_with_api_key(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setenv("OPENWEATHER_API_KEY", "key")
    monkeypatch.setattr(offline_service, "fetch_free_plan_weather", _fake_fetch(calls))
    monkeypatch.setattr(offline_service, "MIN_CALL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(offline_service.Settings, "min_call_interval", 0)
    code = offline_service.main(["--once", "--states", "SP", "--no-air-pollution", "--data-dir", str(tmp_path / "data"), "--site-dir", str(tmp_path / "site")])
    assert code == 0
    assert calls == ["current_weather:SP", "forecast_5d_3h:SP"]
    assert (tmp_path / "data" / "logs" / "offline-service.log").exists()


@pytest.fixture(autouse=True)
def _reset_logger():
    yield
    for handler in list(offline_service.logger.handlers):
        offline_service.logger.removeHandler(handler)
        handler.close()
