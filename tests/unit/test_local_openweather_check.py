from pathlib import Path

from scripts.local_openweather_check import _split_csv, load_env_file, summarize


def test_load_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
# comment
OPENWEATHER_API_KEY="abc123"
OPENWEATHER_LANG=pt_br
""",
        encoding="utf-8",
    )
    values = load_env_file(env_file)
    assert values["OPENWEATHER_API_KEY"] == "abc123"
    assert values["OPENWEATHER_LANG"] == "pt_br"


def test_split_csv_accepts_commas_and_powershell_spaces() -> None:
    assert _split_csv("SP,RJ") == ["SP", "RJ"]
    assert _split_csv("current_weather forecast_5d_3h") == ["current_weather", "forecast_5d_3h"]


def test_summarize_current_weather() -> None:
    summary = summarize("current_weather", {"main": {"temp": 22.5, "humidity": 70, "pressure": 1012}, "weather": [{"description": "ceu limpo"}]})
    assert "temp=22.5C" in summary
    assert "humidity=70%" in summary


def test_summarize_forecast() -> None:
    summary = summarize("forecast_5d_3h", {"list": [{"dt_txt": "2026-06-25 12:00:00", "main": {"temp": 20.0}}]})
    assert "forecast_records=1" in summary
    assert "first_temp=20.0C" in summary
