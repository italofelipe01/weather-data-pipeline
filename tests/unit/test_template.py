from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
import yaml

from shared.daily_table import DAILY_SCHEMA
from shared.forecast_table import FORECAST_SCHEMA
from shared.hourly_table import HOURLY_SCHEMA
from shared.openweather import PRODUCTS

ROOT = Path(__file__).resolve().parents[2]


class _CfnLoader(yaml.SafeLoader):
    pass


def _tag(loader: yaml.SafeLoader, suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return {f"Fn::{suffix}": value}


_CfnLoader.add_multi_constructor("!", _tag)


@pytest.fixture(scope="module")
def resources() -> dict[str, Any]:
    template = yaml.load((ROOT / "template.yaml").read_text(encoding="utf-8"), Loader=_CfnLoader)  # noqa: S506
    return template["Resources"]


def _glue_type(field_type: pa.DataType) -> str:
    for check, name in (
        (pa.types.is_int8, "tinyint"),
        (pa.types.is_int16, "smallint"),
        (pa.types.is_int32, "int"),
        (pa.types.is_int64, "bigint"),
        (pa.types.is_floating, "double"),
        (pa.types.is_string, "string"),
        (pa.types.is_date, "date"),
        (pa.types.is_timestamp, "timestamp"),
    ):
        if check(field_type):
            return name
    raise AssertionError(f"unmapped type {field_type}")


@pytest.mark.parametrize(
    ("resource", "schema"),
    [("HourlyObservationsTable", HOURLY_SCHEMA), ("DailyObservationsTable", DAILY_SCHEMA), ("ForecastTable", FORECAST_SCHEMA)],
)
def test_glue_tables_match_parquet_schemas(resources, resource, schema) -> None:
    table = resources[resource]["Properties"]["TableInput"]
    partitions = {column["Name"] for column in table["PartitionKeys"]}
    declared = [(column["Name"], column["Type"]) for column in table["StorageDescriptor"]["Columns"]]
    expected = [(field.name, _glue_type(field.type)) for field in schema if field.name not in partitions]
    assert declared == expected


def test_handlers_exist(resources) -> None:
    for name, resource in resources.items():
        if resource["Type"] != "AWS::Serverless::Function":
            continue
        module, function = resource["Properties"]["Handler"].rsplit(".", 1)
        source = ROOT / resource["Properties"]["CodeUri"] / (module.replace(".", "/") + ".py")
        assert source.exists(), name
        assert f"def {function}(" in source.read_text(encoding="utf-8"), name


def test_scheduled_products_are_free_plan_products(resources) -> None:
    events = resources["PlannerFunction"]["Properties"]["Events"]
    scheduled = {product for event in events.values() for product in yaml.safe_load(event["Properties"]["Input"])["products"]}
    assert scheduled == set(PRODUCTS)


def test_alarms_fit_cloudwatch_free_tier(resources) -> None:
    alarms = [resource for resource in resources.values() if resource["Type"] == "AWS::CloudWatch::Alarm"]
    assert len(alarms) <= 10
    assert all(alarm["Properties"].get("AlarmActions") for alarm in alarms)


def test_only_curator_gets_the_pyarrow_layer(resources) -> None:
    with_layers = {name for name, resource in resources.items() if resource["Type"] == "AWS::Serverless::Function" and resource["Properties"].get("Layers")}
    assert with_layers == {"CuratorFunction"}
