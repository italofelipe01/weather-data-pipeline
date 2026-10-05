from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

DEFAULT_NAMESPACE = "WeatherDataPipeline"


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    record = {"message": message, **{key: value for key, value in fields.items() if value is not None}}
    logger.log(level, json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str))


def build_metrics_document(metrics: dict[str, float], unit: str = "Count", **properties: Any) -> dict[str, Any]:
    """CloudWatch Embedded Metric Format document with a single low-cardinality dimension (Pipeline)."""
    pipeline = os.getenv("PIPELINE_NAME", "local")
    return {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": os.getenv("METRICS_NAMESPACE", DEFAULT_NAMESPACE),
                    "Dimensions": [["Pipeline"]],
                    "Metrics": [{"Name": name, "Unit": unit} for name in metrics],
                }
            ],
        },
        **{key: value for key, value in properties.items() if value is not None},
        "Pipeline": pipeline,
        "FunctionName": os.getenv("AWS_LAMBDA_FUNCTION_NAME", "local"),
        **metrics,
    }


def emit_metrics(metrics: dict[str, float], unit: str = "Count", **properties: Any) -> None:
    """Write EMF straight to stdout.

    The Lambda Python runtime prefixes records emitted through `logging` with level, timestamp and request id,
    which stops CloudWatch from extracting EMF metrics. A raw JSON line on stdout is always parsed.
    """
    if not metrics or os.getenv("METRICS_DISABLED", "").lower() == "true":
        return
    document = build_metrics_document(metrics, unit, **properties)
    sys.stdout.write(json.dumps(document, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
    sys.stdout.flush()
