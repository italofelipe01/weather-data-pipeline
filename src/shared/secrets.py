from __future__ import annotations

import os
import time
from typing import Any

_cached_value: str | None = None
_cached_until = 0.0


def reset_api_key_cache() -> None:
    global _cached_value, _cached_until
    _cached_value = None
    _cached_until = 0.0


def get_openweather_api_key(ssm_client: Any, parameter_name: str) -> str:
    global _cached_value, _cached_until
    now = time.time()
    if _cached_value and now < _cached_until:
        return _cached_value
    response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
    value = response.get("Parameter", {}).get("Value", "")
    if not value:
        raise RuntimeError("OpenWeather API key parameter is empty")
    _cached_value = value
    _cached_until = now + int(os.getenv("API_KEY_CACHE_TTL_SECONDS", "300"))
    return value
