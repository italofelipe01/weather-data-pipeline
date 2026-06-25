from shared.capitals import BRAZIL_CAPITALS, get_capitals


def test_has_all_27_capitals() -> None:
    assert len(BRAZIL_CAPITALS) == 27
    assert len({capital["state"] for capital in BRAZIL_CAPITALS}) == 27


def test_filter_capitals_by_state() -> None:
    capitals = get_capitals(["SP", "RJ"])
    assert [capital["state"] for capital in capitals] == ["RJ", "SP"]
