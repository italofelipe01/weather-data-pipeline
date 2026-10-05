"""Run the whole pipeline on this machine with the real OpenWeather API and a filesystem-backed S3.

    python scripts/local_pipeline.py --states SP,RJ --products all
    python -m http.server 8000 --directory frontend

Calls are spaced to stay below the Free plan limit of 60 calls/minute. No AWS account is needed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("METRICS_DISABLED", "true")

from curator.handler import CuratorConfig, run  # noqa: E402
from publisher.handler import PublisherConfig, publish_latest  # noqa: E402
from scripts.local_openweather_check import _split_csv, load_env_file, summarize  # noqa: E402
from scripts.local_s3 import LocalDirS3  # noqa: E402
from shared.capitals import get_capitals  # noqa: E402
from shared.openweather import SourceError, fetch_free_plan_weather  # noqa: E402
from shared.source_plan import FREE_PLAN_CALLS_PER_MINUTE, build_collection_jobs, parse_products, utc_snapshot  # noqa: E402
from shared.storage import build_source_key, build_source_object, put_json_once  # noqa: E402
from shared.time_utils import iso_z  # noqa: E402

RAW_BUCKET = "local-raw"
SITE_BUCKET = "local-site"


def collect(s3: LocalDirS3, jobs: list[dict[str, object]], api_key: str, min_interval: float, timeout: int) -> tuple[int, int]:
    stored = failures = 0
    last_call = 0.0
    for job in jobs:
        wait = min_interval - (time.monotonic() - last_call)
        if wait > 0:
            time.sleep(wait)
        last_call = time.monotonic()
        label = f"{job['state']} {job['city']} {job['product']}"
        try:
            payload = fetch_free_plan_weather(job, api_key, timeout_seconds=timeout)
        except SourceError as exc:
            failures += 1
            print(f"ERRO {label}: {exc}", file=sys.stderr)
            continue
        outcome = put_json_once(s3, RAW_BUCKET, build_source_key(job), build_source_object(job, payload))
        stored += 1
        print(f"OK {label} ({outcome}): {summarize(str(job['product']), payload)}")
    return stored, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa coleta, curadoria e publicacao localmente com a API real da OpenWeather.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--states", default="", help="UFs separadas por virgula (padrao: todas as 27)")
    parser.add_argument("--products", default="all", help="current_weather, forecast_5d_3h, air_pollution, air_pollution_forecast ou all")
    parser.add_argument("--raw-dir", default=".local-data/raw")
    parser.add_argument("--site-dir", default="frontend")
    parser.add_argument("--skip-fetch", action="store_true", help="Reprocessa apenas os dados raw ja coletados")
    parser.add_argument("--timeout-seconds", type=int, default=15)
    args = parser.parse_args()

    s3 = LocalDirS3({RAW_BUCKET: ROOT / args.raw_dir, SITE_BUCKET: ROOT / args.site_dir})
    now = datetime.now(UTC)
    if not args.skip_fetch:
        env_values = load_env_file(ROOT / args.env_file)
        api_key = os.getenv("OPENWEATHER_API_KEY") or env_values.get("OPENWEATHER_API_KEY", "")
        if not api_key or api_key == "SUA_API_KEY_AQUI":
            print("OPENWEATHER_API_KEY nao encontrada. Preencha o .env (veja .env.example).", file=sys.stderr)
            return 2
        states = _split_csv(args.states.upper()) or None
        jobs = build_collection_jobs(
            get_capitals(states),
            parse_products(_split_csv(args.products)),
            env_values.get("OPENWEATHER_UNITS", "metric"),
            env_values.get("OPENWEATHER_LANG", "pt_br"),
            utc_snapshot(now),
        )
        interval = 60 / (FREE_PLAN_CALLS_PER_MINUTE - 5)
        print(f"{len(jobs)} chamadas, uma a cada {interval:.2f}s (abaixo de {FREE_PLAN_CALLS_PER_MINUTE}/min)...")
        stored, failures = collect(s3, jobs, api_key, interval, args.timeout_seconds)
        print(f"Coleta concluida: {stored} gravados, {failures} falhas.")
        now = datetime.now(UTC)

    # Locally the current (still open) hour is curated too, so the dashboard has something to plot right away.
    config = CuratorConfig(raw_bucket=RAW_BUCKET, site_bucket=SITE_BUCKET)
    curation = run({"target_hour": iso_z(now), "rebuild_serving": True}, s3, config, now + timedelta(hours=1))
    latest = publish_latest(s3, PublisherConfig(raw_bucket=RAW_BUCKET, site_bucket=SITE_BUCKET), now)
    print(json.dumps({"curated_records": curation["records"], "published": curation["published"], "latest": latest}, indent=2, default=str))
    print(f"\nDashboard: python -m http.server 8000 --directory {args.site_dir}  ->  http://localhost:8000/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
