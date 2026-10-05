"""Run the whole weather pipeline on this machine, without AWS.

Same code, cadence and data layout as the cloud stack:

- collects the OpenWeather Free plan APIs on the cloud schedule, spaced under 60 calls/minute;
- enforces the monthly call limit with a local counter;
- curates the hourly, daily and forecast Parquet tables (catching up missed hours) and the dashboard JSON;
- publishes the latest observation of every capital every 10 minutes;
- serves the dashboard at http://127.0.0.1:8000;
- deletes raw snapshots older than the retention period.

    python scripts/offline_service.py            # runs until Ctrl+C
    python scripts/offline_service.py --once     # one full cycle, then exits

Only the OpenWeather requests need internet access. Data lives in .local-data/ (Parquet tables can be queried
with scripts/query_local.py) and the dashboard JSON in frontend/data/.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import signal
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("METRICS_DISABLED", "true")

from curator.handler import CuratorConfig  # noqa: E402
from curator.handler import run as run_curator  # noqa: E402
from publisher.handler import PublisherConfig, publish_latest  # noqa: E402
from scripts.local_openweather_check import _split_csv, load_env_file  # noqa: E402
from scripts.local_s3 import LocalDirS3  # noqa: E402
from shared.call_budget import FileCallCounter, budget_status  # noqa: E402
from shared.capitals import get_capitals  # noqa: E402
from shared.collection import build_batch_job, build_batch_key, collect_batch  # noqa: E402
from shared.openweather import fetch_free_plan_weather  # noqa: E402
from shared.source_plan import FREE_PLAN_CALLS_PER_MINUTE, MONTHLY_OPERATIONAL_CALL_LIMIT, utc_snapshot  # noqa: E402
from shared.storage import put_json_once  # noqa: E402
from shared.time_utils import floor_minute, iso_z, parse_utc  # noqa: E402

LAKE_BUCKET = "local-lake"
SITE_BUCKET = "local-site"
# A little below 60/minute so retries never push a 60-second window over the Free plan limit.
MIN_CALL_INTERVAL_SECONDS = 60 / (FREE_PLAN_CALLS_PER_MINUTE - 5)

logger = logging.getLogger("offline_service")


@dataclass(frozen=True)
class Schedule:
    """Fires every `every_minutes` minutes, or at `minute` past every `every_hours`-th hour (UTC)."""

    every_minutes: int | None = None
    minute: int = 0
    every_hours: int = 1

    def previous_fire(self, now: datetime) -> datetime:
        now = floor_minute(now)
        if self.every_minutes:
            return now.replace(minute=(now.minute // self.every_minutes) * self.every_minutes)
        candidate = now.replace(minute=self.minute)
        if candidate > now:
            candidate -= timedelta(hours=1)
        while candidate.hour % self.every_hours:
            candidate -= timedelta(hours=1)
        return candidate


@dataclass(frozen=True)
class Task:
    name: str
    schedule: Schedule
    action: Callable[[datetime], Any]


@dataclass
class Settings:
    data_dir: Path
    site_dir: Path
    api_key: str
    interval_minutes: int = 3
    air_pollution: bool = True
    states: list[str] | None = None
    monthly_limit: int = MONTHLY_OPERATIONAL_CALL_LIMIT
    catchup_hours: int = 48
    raw_retention_days: int = 30
    units: str = "metric"
    lang: str = "pt_br"
    min_call_interval: float = MIN_CALL_INTERVAL_SECONDS
    timeout_seconds: int = 15

    @property
    def lake_dir(self) -> Path:
        return self.data_dir / "lake"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"


class OfflinePipeline:
    def __init__(
        self,
        settings: Settings,
        fetch: Callable[..., dict[str, Any]] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings
        self.fetch = fetch or fetch_free_plan_weather
        self.sleep = sleep
        self.s3 = LocalDirS3({LAKE_BUCKET: settings.lake_dir, SITE_BUCKET: settings.site_dir})
        self.counter = FileCallCounter(settings.state_dir / "call-counter.json")
        self.state_file = settings.state_dir / "scheduler.json"
        self.capitals = get_capitals(settings.states)
        self.tasks = self._tasks()

    def _tasks(self) -> list[Task]:
        tasks = [
            Task("collect:current_weather", Schedule(every_minutes=self.settings.interval_minutes), partial(self.collect, "current_weather")),
            Task("collect:forecast_5d_3h", Schedule(minute=5), partial(self.collect, "forecast_5d_3h")),
        ]
        if self.settings.air_pollution:
            tasks += [
                Task("collect:air_pollution", Schedule(minute=35), partial(self.collect, "air_pollution")),
                Task("collect:air_pollution_forecast", Schedule(minute=50, every_hours=6), partial(self.collect, "air_pollution_forecast")),
            ]
        return [
            *tasks,
            Task("curate", Schedule(minute=20), self.curate),
            Task("publish", Schedule(every_minutes=10), self.publish),
            Task("prune", Schedule(minute=40, every_hours=24), self.prune),
        ]

    # -- actions -------------------------------------------------------------------------------------------

    def collect(self, product: str, now: datetime) -> dict[str, Any]:
        calls = len(self.capitals)
        status = budget_status(self.counter.read(now), self.settings.monthly_limit, now)
        if not status.allows(calls):
            logger.warning("collection skipped: monthly limit reached (%s of %s calls)", status.used, status.limit)
            return {"product": product, "outcome": "monthly_call_limit"}
        batch_job = build_batch_job(product, self.capitals, self.settings.units, self.settings.lang, utc_snapshot(now))
        result = collect_batch(
            batch_job,
            lambda job: self.fetch(job, self.settings.api_key, timeout_seconds=self.settings.timeout_seconds),
            min_interval=self.settings.min_call_interval,
            sleep=self.sleep,
        )
        self.counter.add(now, result.calls)
        outcome = "no_data"
        if result.items:
            key = build_batch_key(product, result.snapshot_at, [capital["state"] for capital in self.capitals])
            outcome = put_json_once(self.s3, LAKE_BUCKET, key, result.raw_object())
        problems = "; ".join(f"{item['state']}: {item['error']}" for item in [*result.failures, *result.rejected])
        log = logger.warning if problems else logger.info
        log("collected %s: %s/%s capitals, %s calls%s", product, len(result.items), calls, result.calls, f" ({problems})" if problems else "")
        return {"product": product, "outcome": outcome, "collected": len(result.items), "calls": result.calls}

    def curate(self, now: datetime) -> dict[str, Any]:
        config = CuratorConfig(raw_bucket=LAKE_BUCKET, site_bucket=SITE_BUCKET, lookback_hours=self.settings.catchup_hours)
        result = run_curator({}, self.s3, config, now)
        logger.info(
            "curated %s hours, %s forecasts, daily %s, published %s",
            result["hours_written"],
            result["forecasts_written"],
            [item["date"] for item in result["daily"] if item["status"] == "written"],
            result["published"],
        )
        return result

    def publish(self, now: datetime) -> dict[str, Any]:
        config = PublisherConfig(raw_bucket=LAKE_BUCKET, site_bucket=SITE_BUCKET, call_limit=self.settings.monthly_limit, runtime="local")
        result = publish_latest(self.s3, config, now, self.counter)
        logger.info("published latest: %s capitals, latest observation %s", result["current_capitals"], result["latest_observation_at"])
        return result

    def prune(self, now: datetime) -> int:
        return prune_raw(self.settings.lake_dir, self.settings.raw_retention_days, now)

    # -- scheduling ----------------------------------------------------------------------------------------

    def _load_state(self) -> dict[str, str]:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8")).get("last_run", {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_state(self, last_run: dict[str, str]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({"last_run": last_run}, indent=2), encoding="utf-8")

    def run_due(self, now: datetime | None = None, clock: Callable[[], datetime] | None = None) -> list[str]:
        """Run every task whose latest scheduled time has not been handled yet (missed runs execute once)."""
        clock = clock or (lambda: datetime.now(UTC))
        now = now or clock()
        last_run = self._load_state()
        ran: list[str] = []
        for task in self.tasks:
            fire = task.schedule.previous_fire(now)
            previous = last_run.get(task.name)
            if previous is not None and parse_utc(previous) >= fire:
                continue
            started = clock()
            try:
                task.action(started)
            except Exception:
                logger.exception("task %s failed", task.name)
            last_run[task.name] = iso_z(started)
            self._save_state(last_run)
            ran.append(task.name)
        return ran

    def run_once(self, clock: Callable[[], datetime] | None = None) -> list[str]:
        """Collect every enabled product now, then curate and publish (closed hours only)."""
        clock = clock or (lambda: datetime.now(UTC))
        names = [task.name for task in self.tasks if task.name.startswith("collect:")] + ["curate", "publish"]
        actions = {task.name: task.action for task in self.tasks}
        for name in names:
            try:
                actions[name](clock())
            except Exception:
                logger.exception("task %s failed", name)
        return names

    def run_forever(self, stop: threading.Event) -> None:
        logger.info("offline service started (data in %s)", self.settings.data_dir)
        while not stop.is_set():
            self.run_due()
            now = datetime.now(UTC)
            stop.wait(60 - now.second - now.microsecond / 1_000_000 + 1)
        logger.info("offline service stopped")


_DAY_DIR = re.compile(r"year=(\d{4})[/\\]month=(\d{2})[/\\]day=(\d{2})$")


def prune_raw(lake_dir: Path, retention_days: int, now: datetime) -> int:
    """Delete raw day partitions older than the retention (0 keeps everything). Curated tables are kept."""
    raw_root = Path(lake_dir) / "raw"
    if retention_days <= 0 or not raw_root.is_dir():
        return 0
    cutoff = (now - timedelta(days=retention_days)).date()
    removed = 0
    for day_dir in sorted(raw_root.glob("*/product=*/year=*/month=*/day=*")):
        match = _DAY_DIR.search(str(day_dir))
        if match and date(int(match.group(1)), int(match.group(2)), int(match.group(3))) < cutoff:
            shutil.rmtree(day_dir, ignore_errors=True)
            removed += 1
    if removed:
        logger.info("pruned %s raw day partitions older than %s days", removed, retention_days)
    return removed


class DashboardHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        if self.path.startswith("/data/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature defined by the base class
        logger.debug("http %s", format % args)


def start_dashboard(site_dir: Path, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), partial(DashboardHandler, directory=str(site_dir)))
    threading.Thread(target=server.serve_forever, name="dashboard", daemon=True).start()
    return server


def configure_logging(data_dir: Path, level: str) -> None:
    logger.setLevel(level)
    logging.getLogger().setLevel(logging.WARNING)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(data_dir / "logs" / "offline-service.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if sys.stdout is not None:  # pythonw (Windows scheduled task) has no console
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        logger.addHandler(console)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline de clima completo na sua maquina, sem AWS.")
    parser.add_argument("--once", action="store_true", help="Coleta todos os produtos, faz a curadoria, publica e encerra")
    parser.add_argument("--no-server", action="store_true", help="Nao servir o dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 para acessar de outros dispositivos da rede")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--interval-minutes", type=int, choices=[3, 5, 10, 15, 30], default=3, help="Cadencia da Current Weather")
    parser.add_argument("--no-air-pollution", action="store_true")
    parser.add_argument("--states", default="", help="UFs separadas por virgula (padrao: as 27 capitais)")
    parser.add_argument("--monthly-limit", type=int, default=MONTHLY_OPERATIONAL_CALL_LIMIT)
    parser.add_argument("--catchup-hours", type=int, default=48, help="Horas verificadas pela curadoria a cada execucao")
    parser.add_argument("--raw-retention-days", type=int, default=30, help="0 mantem o raw para sempre")
    parser.add_argument("--data-dir", default=".local-data")
    parser.add_argument("--site-dir", default="frontend")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_dir = ROOT / args.data_dir
    site_dir = ROOT / args.site_dir
    configure_logging(data_dir, args.log_level)
    env_values = load_env_file(ROOT / args.env_file)
    api_key = os.getenv("OPENWEATHER_API_KEY") or env_values.get("OPENWEATHER_API_KEY", "")
    if not api_key or api_key == "SUA_API_KEY_AQUI":
        logger.error("OPENWEATHER_API_KEY nao encontrada: preencha o .env (veja .env.example) ou defina a variavel de ambiente.")
        return 2
    settings = Settings(
        data_dir=data_dir,
        site_dir=site_dir,
        api_key=api_key,
        interval_minutes=args.interval_minutes,
        air_pollution=not args.no_air_pollution,
        states=_split_csv(args.states.upper()) or None,
        monthly_limit=args.monthly_limit,
        catchup_hours=args.catchup_hours,
        raw_retention_days=args.raw_retention_days,
        units=env_values.get("OPENWEATHER_UNITS", "metric"),
        lang=env_values.get("OPENWEATHER_LANG", "pt_br"),
    )
    pipeline = OfflinePipeline(settings)
    if args.once:
        pipeline.run_once()
        return 0

    server = None
    if not args.no_server:
        try:
            server = start_dashboard(site_dir, args.host, args.port)
        except OSError as exc:
            logger.error("nao foi possivel abrir a porta %s (%s); use --port", args.port, exc)
            return 3
        logger.info("dashboard em http://%s:%s/", "localhost" if args.host in {"127.0.0.1", "0.0.0.0"} else args.host, args.port)

    stop = threading.Event()
    for name in ("SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.set())
    try:
        pipeline.run_forever(stop)
    except KeyboardInterrupt:
        stop.set()
    finally:
        if server is not None:
            server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
