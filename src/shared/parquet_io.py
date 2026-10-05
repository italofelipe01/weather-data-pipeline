from __future__ import annotations

import io
from datetime import UTC, date, datetime
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from shared.time_utils import parse_utc

PARQUET_CONTENT_TYPE = "application/vnd.apache.parquet"


def _coerce(value: Any, field_type: pa.DataType) -> Any:
    if value is None:
        return None
    if pa.types.is_timestamp(field_type):
        # Stored as naive UTC (isAdjustedToUTC=false) to stay compatible with files already written.
        return parse_utc(value).replace(tzinfo=None)
    if pa.types.is_date(field_type):
        if isinstance(value, datetime):
            return value.date()
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if pa.types.is_integer(field_type):
        return int(value)
    if pa.types.is_floating(field_type):
        return float(value)
    if pa.types.is_string(field_type):
        return str(value)
    return value


def records_to_parquet(records: list[dict[str, Any]], schema: pa.Schema) -> bytes:
    rows = [{field.name: _coerce(record.get(field.name), field.type) for field in schema} for record in records]
    table = pa.Table.from_pylist(rows, schema=schema)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


def parquet_to_records(body: bytes) -> list[dict[str, Any]]:
    """Read Parquet rows back; timestamps come back as aware UTC datetimes."""
    rows = pq.read_table(io.BytesIO(body)).to_pylist()
    for row in rows:
        for key, value in row.items():
            if isinstance(value, datetime) and value.tzinfo is None:
                row[key] = value.replace(tzinfo=UTC)
    return rows
