from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any


def values(rows: Iterable[dict[str, Any]], key: str) -> list[float]:
    return [float(value) for row in rows if (value := row.get(key)) is not None]


def mean(numbers: Sequence[float], digits: int = 4) -> float | None:
    return round(statistics.fmean(numbers), digits) if numbers else None


def minimum(numbers: Sequence[float]) -> float | None:
    return min(numbers) if numbers else None


def maximum(numbers: Sequence[float]) -> float | None:
    return max(numbers) if numbers else None


def total(numbers: Sequence[float], digits: int = 4) -> float | None:
    return round(math.fsum(numbers), digits) if numbers else None


def circular_mean_deg(degrees: Sequence[float]) -> float | None:
    """Mean wind direction: averaging 350 and 10 degrees must give 0, not 180."""
    if not degrees:
        return None
    sin_sum = sum(math.sin(math.radians(value)) for value in degrees)
    cos_sum = sum(math.cos(math.radians(value)) for value in degrees)
    if abs(sin_sum) < 1e-9 and abs(cos_sum) < 1e-9:
        return None
    return round(math.degrees(math.atan2(sin_sum, cos_sum)) % 360, 1)


def mode(items: Sequence[Any]) -> Any | None:
    """Most frequent non-null item; ties go to the most recent occurrence."""
    present = [item for item in items if item is not None]
    if not present:
        return None
    counts = Counter(present)
    best = max(counts.values())
    for item in reversed(present):
        if counts[item] == best:
            return item
    return None  # pragma: no cover
