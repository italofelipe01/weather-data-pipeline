import pytest

from shared.capitals import BRAZIL_CAPITALS, REGIONS, capital_by_state, get_capitals


def test_has_all_27_capitals() -> None:
    assert len(BRAZIL_CAPITALS) == 27
    assert len({capital["state"] for capital in BRAZIL_CAPITALS}) == 27


def test_filter_capitals_by_state() -> None:
    capitals = get_capitals(["SP", "rj"])
    assert [capital["state"] for capital in capitals] == ["RJ", "SP"]


def test_unknown_state_is_rejected() -> None:
    with pytest.raises(ValueError, match="XX"):
        get_capitals(["SP", "XX"])


def test_every_capital_has_region_and_brazilian_offset() -> None:
    assert {capital["region"] for capital in BRAZIL_CAPITALS} == set(REGIONS)
    assert {capital["utc_offset_seconds"] for capital in BRAZIL_CAPITALS} == {-3 * 3600, -4 * 3600, -5 * 3600}
    assert capital_by_state("ac")["utc_offset_seconds"] == -5 * 3600
    assert capital_by_state("SP")["display_name"] == "São Paulo"
    assert capital_by_state("ZZ") is None
