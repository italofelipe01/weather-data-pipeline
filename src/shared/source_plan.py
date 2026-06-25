from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from shared.capitals import Capital

FREE_PLAN_PRODUCTS = {"current_weather", "forecast_5d_3h"}
MONTHLY_FREE_CALL_LIMIT = 1_000_000
MONTHLY_OPERATIONAL_CALL_LIMIT = 500_000


def parse_products(value: object | None) -> list[str]:
    if value is None:
        return ["current_weather"]
    if isinstance(value, str):
        products = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, list):
        products = [str(item).strip() for item in value if str(item).strip()]
    else:
        raise ValueError("products must be a list or comma-separated string")
    unknown = sorted(set(products) - FREE_PLAN_PRODUCTS)
    if unknown:
        raise ValueError(f"unsupported OpenWeather free-plan products: {', '.join(unknown)}")
    return products


def utc_snapshot(value: object | None = None) -> str:
    if value:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
        return parsed.replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")
    return datetime.now(UTC).replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")


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
