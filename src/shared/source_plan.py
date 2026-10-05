from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from shared.capitals import BRAZIL_CAPITALS, Capital
from shared.openweather import PRODUCTS
from shared.time_utils import floor_minute, iso_z

FREE_PLAN_PRODUCTS = frozenset(PRODUCTS)
MONTHLY_FREE_CALL_LIMIT = 1_000_000
MONTHLY_OPERATIONAL_CALL_LIMIT = 500_000
FREE_PLAN_CALLS_PER_MINUTE = 60

# Default cadence configured in template.yaml when EnableSchedules=true.
DEFAULT_RUNS_PER_DAY: dict[str, int] = {
    "current_weather": 24 * 20,  # every 3 minutes
    "forecast_5d_3h": 24,  # hourly
    "air_pollution": 24,  # hourly
    "air_pollution_forecast": 4,  # every 6 hours
}


def parse_products(value: object | None) -> list[str]:
    if value is None:
        return ["current_weather"]
    if isinstance(value, str):
        products = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, list | tuple):
        products = [str(item).strip() for item in value if str(item).strip()]
    else:
        raise ValueError("products must be a list or comma-separated string")
    if products == ["all"]:
        return list(PRODUCTS)
    unknown = sorted(set(products) - FREE_PLAN_PRODUCTS)
    if unknown:
        raise ValueError(f"unsupported OpenWeather free-plan products: {', '.join(unknown)}")
    return list(dict.fromkeys(products))


def utc_snapshot(value: object | None = None) -> str:
    return iso_z(floor_minute(value if value else datetime.now(UTC)))


def projected_monthly_calls(runs_per_day: Mapping[str, int] | None = None, capitals: int = len(BRAZIL_CAPITALS), days: int = 31) -> int:
    cadence = DEFAULT_RUNS_PER_DAY if runs_per_day is None else runs_per_day
    return sum(runs * capitals * days for runs in cadence.values())


def build_collection_jobs(
    capitals: Iterable[Capital],
    products: list[str],
    units: str,
    lang: str,
    snapshot_at: str,
) -> list[dict[str, object]]:
    return [
        {
            "source": "openweather-free-plan",
            "product": product,
            "city": capital["city"],
            "state": capital["state"],
            "ibge_code": capital["ibge_code"],
            "latitude": capital["latitude"],
            "longitude": capital["longitude"],
            "timezone": capital["timezone"],
            "snapshot_at": snapshot_at,
            "units": units,
            "lang": lang,
        }
        for capital in capitals
        for product in products
    ]
