import json
import logging

from shared.structured_logging import emit_metrics, log_event


def test_emit_metrics_writes_raw_emf_json_to_stdout(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PIPELINE_NAME", "weather-data-pipeline-dev")
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "collector")
    monkeypatch.delenv("METRICS_DISABLED", raising=False)
    emit_metrics({"OpenWeatherApiCalls": 5, "SourceJobFailures": 0}, product="current_weather")
    line = capsys.readouterr().out.strip()
    document = json.loads(line)
    directive = document["_aws"]["CloudWatchMetrics"][0]
    assert directive["Namespace"] == "WeatherDataPipeline"
    assert directive["Dimensions"] == [["Pipeline"]]
    assert [metric["Name"] for metric in directive["Metrics"]] == ["OpenWeatherApiCalls", "SourceJobFailures"]
    assert document["Pipeline"] == "weather-data-pipeline-dev"
    assert document["OpenWeatherApiCalls"] == 5
    assert document["product"] == "current_weather"


def test_emit_metrics_can_be_disabled(monkeypatch, capsys) -> None:
    monkeypatch.setenv("METRICS_DISABLED", "true")
    emit_metrics({"X": 1})
    emit_metrics({})
    assert capsys.readouterr().out == ""


def test_log_event_drops_none_fields(caplog) -> None:
    logger = logging.getLogger("test-structured")
    with caplog.at_level(logging.INFO, logger="test-structured"):
        log_event(logger, logging.INFO, "hello", city="Recife", missing=None)
    assert json.loads(caplog.records[0].getMessage()) == {"message": "hello", "city": "Recife"}
