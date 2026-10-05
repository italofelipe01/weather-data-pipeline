from shared.aggregation import circular_mean_deg, maximum, mean, minimum, mode, total, values


def test_basic_statistics_ignore_missing_values() -> None:
    rows = [{"x": 1}, {"x": None}, {"x": 3}, {}]
    assert values(rows, "x") == [1.0, 3.0]
    assert mean([1.0, 2.0]) == 1.5
    assert mean([]) is None
    assert minimum([]) is None and maximum([]) is None and total([]) is None
    assert total([0.1, 0.2]) == 0.3


def test_circular_mean_wraps_around_north() -> None:
    assert circular_mean_deg([350.0, 10.0]) in (0.0, 360.0)
    assert circular_mean_deg([90.0, 90.0]) == 90.0
    assert circular_mean_deg([0.0, 180.0]) is None
    assert circular_mean_deg([]) is None


def test_mode_prefers_most_recent_on_ties() -> None:
    assert mode(["Clouds", "Rain", "Rain", "Clouds"]) == "Clouds"
    assert mode(["Rain", "Rain", "Clear"]) == "Rain"
    assert mode([None, None]) is None
