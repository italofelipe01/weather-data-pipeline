import pytest

from shared.capitals import get_capitals
from shared.source_plan import (
    DEFAULT_RUNS_PER_DAY,
    FREE_PLAN_CALLS_PER_MINUTE,
    MONTHLY_FREE_CALL_LIMIT,
    MONTHLY_OPERATIONAL_CALL_LIMIT,
    build_collection_jobs,
    parse_products,
    projected_monthly_calls,
    utc_snapshot,
)


def test_monthly_operational_limit_is_50_percent_of_free_plan() -> None:
    assert MONTHLY_OPERATIONAL_CALL_LIMIT == MONTHLY_FREE_CALL_LIMIT // 2 == 500_000


def test_default_cadence_fits_the_operational_limit_even_in_31_day_months() -> None:
    assert projected_monthly_calls(days=31) == 445_284
    assert projected_monthly_calls(days=31) <= MONTHLY_OPERATIONAL_CALL_LIMIT
    assert projected_monthly_calls(days=30) == 430_920


def test_no_two_product_bursts_exceed_the_per_minute_limit() -> None:
    # Each schedule fires 27 calls (one per capital); at most two schedules share any 60-second window.
    assert FREE_PLAN_CALLS_PER_MINUTE > 2 * 27
    assert set(DEFAULT_RUNS_PER_DAY) == {"current_weather", "forecast_5d_3h", "air_pollution", "air_pollution_forecast"}


def test_parse_products_accepts_list_and_string() -> None:
    assert parse_products(["current_weather", "forecast_5d_3h"]) == ["current_weather", "forecast_5d_3h"]
    assert parse_products("current_weather,forecast_5d_3h") == ["current_weather", "forecast_5d_3h"]
    assert parse_products("air_pollution, air_pollution,current_weather") == ["air_pollution", "current_weather"]
    assert parse_products(None) == ["current_weather"]
    assert parse_products("all") == ["current_weather", "forecast_5d_3h", "air_pollution", "air_pollution_forecast"]


def test_parse_products_rejects_paid_or_unknown_product() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        parse_products(["one_call_4"])
    with pytest.raises(ValueError, match="list"):
        parse_products(42)


def test_utc_snapshot_rounds_to_minute() -> None:
    assert utc_snapshot("2026-06-25T12:34:56Z") == "2026-06-25T12:34:00Z"
    assert utc_snapshot().endswith(":00Z")


def test_builds_jobs_for_each_capital_and_product() -> None:
    jobs = build_collection_jobs(get_capitals(["SP"]), ["current_weather", "forecast_5d_3h"], "metric", "pt_br", "2026-06-25T12:00:00Z")
    assert len(jobs) == 2
    assert jobs[0]["source"] == "openweather-free-plan"
    assert jobs[0]["city"] == "Sao Paulo"
    assert jobs[0]["product"] == "current_weather"
    assert jobs[1]["product"] == "forecast_5d_3h"
