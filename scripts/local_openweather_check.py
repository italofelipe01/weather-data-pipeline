from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from shared.capitals import get_capitals  # noqa: E402
from shared.openweather import SourceError, fetch_free_plan_weather  # noqa: E402
from shared.source_plan import build_collection_jobs, parse_products, utc_snapshot  # noqa: E402


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,\s]+", value) if item.strip()]


def summarize(product: str, payload: dict[str, Any]) -> str:
    if product == "current_weather":
        main = payload.get("main", {})
        weather = payload.get("weather", [{}])
        description = weather[0].get("description") if weather else None
        return f"temp={main.get('temp')}C humidity={main.get('humidity')}% pressure={main.get('pressure')}hPa description={description}"
    records = payload.get("list", [])
    first = records[0] if records else {}
    main = first.get("main", {})
    return f"forecast_records={len(records)} first_dt={first.get('dt_txt')} first_temp={main.get('temp')}C"


def main() -> int:
    parser = argparse.ArgumentParser(description="Testa a OpenWeather localmente, sem AWS CLI e sem deploy.")
    parser.add_argument("--env-file", default=".env", help="Arquivo local com OPENWEATHER_API_KEY. Padrao: .env")
    parser.add_argument("--api-key", default="", help="Opcional. Prefira .env para nao deixar a chave no historico do terminal.")
    parser.add_argument("--states", default="SP", help="UFs separadas por virgula. Exemplo: SP,RJ")
    parser.add_argument("--products", default="current_weather", help="current_weather, forecast_5d_3h ou ambos separados por virgula")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    args = parser.parse_args()

    env_values = load_env_file(ROOT / args.env_file)
    api_key = args.api_key or os.getenv("OPENWEATHER_API_KEY") or env_values.get("OPENWEATHER_API_KEY", "")
    if not api_key:
        print("OPENWEATHER_API_KEY nao encontrada. Crie um .env local ou passe --api-key.", file=sys.stderr)
        return 2

    products = parse_products(_split_csv(args.products))
    states = _split_csv(args.states.upper())
    jobs = build_collection_jobs(
        get_capitals(states), products, env_values.get("OPENWEATHER_UNITS", "metric"), env_values.get("OPENWEATHER_LANG", "pt_br"), utc_snapshot()
    )
    if not jobs:
        print("Nenhum job gerado. Verifique as UFs informadas.", file=sys.stderr)
        return 2

    failures = 0
    for job in jobs:
        label = f"{job['state']} {job['city']} {job['product']}"
        try:
            payload = fetch_free_plan_weather(job, api_key, timeout_seconds=args.timeout_seconds)
            print(f"OK {label}: {summarize(str(job['product']), payload)}")
        except SourceError as exc:
            failures += 1
            print(f"ERRO {label}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
