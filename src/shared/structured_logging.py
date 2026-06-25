from __future__ import annotations

import json
import logging
import os
import time
from typing import Any


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    record = {"message": message, **{key: value for key, value in fields.items() if value is not None}}
    logger.log(level, json.dumps(record, ensure_ascii=False, separators=(",", ":")))


def log_count_metric(logger: logging.Logger, metric_name: str, **fields: Any) -> None:
    function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME", "local")
    record = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": "WeatherDataPipeline",
                    "Dimensions": [["FunctionName"]],
                    "Metrics": [{"Name": metric_name, "Unit": "Count"}],
                }
            ],
        },
        "FunctionName": function_name,
        metric_name: 1,
        **{key: value for key, value in fields.items() if value is not None},
    }
    logger.error(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
