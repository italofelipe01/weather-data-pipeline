from shared.capitals import get_capitals
from shared.source_plan import MONTHLY_OPERATIONAL_CALL_LIMIT, build_collection_jobs, parse_products, utc_snapshot


def test_monthly_operational_limit_is_50_percent_of_free_plan() -> None:
    assert MONTHLY_OPERATIONAL_CALL_LIMIT == 500_000


def test_parse_products_accepts_list_and_string() -> None:
    assert parse_products(["current_weather", "forecast_5d_3h"]) == ["current_weather", "forecast_5d_3h"]
    assert parse_products("current_weather,forecast_5d_3h") == ["current_weather", "forecast_5d_3h"]


def test_parse_products_rejects_paid_or_unknown_product() -> None:
    try:
        parse_products(["one_call_4"])
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_utc_snapshot_rounds_to_minute() -> None:
    assert utc_snapshot("2026-06-25T12:34:56Z") == "2026-06-25T12:34:00Z"


def test_builds_jobs_for_each_capital_and_product() -> None:
    jobs = build_collection_jobs(get_capitals(["SP"]), ["current_weather", "forecast_5d_3h"], "metric", "pt_br", "2026-06-25T12:00:00Z")
    assert len(jobs) == 2
    assert jobs[0]["source"] == "openweather-free-plan"
    assert jobs[0]["city"] == "Sao Paulo"
    assert jobs[0]["product"] == "current_weather"
    assert jobs[1]["product"] == "forecast_5d_3h"
