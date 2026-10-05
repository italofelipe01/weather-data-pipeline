"""Query the local Parquet tables with DuckDB, using the same SQL and table names as Athena.

python scripts/query_local.py queries/monthly_from_daily.sql
python scripts/query_local.py --sql "SELECT state, max(temperature_max) FROM weather_daily_observations GROUP BY 1"
python scripts/query_local.py queries/air_quality.sql --output relatorio.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TABLES = {
    "weather_hourly_observations": "hourly_observations",
    "weather_daily_observations": "daily_observations",
    "weather_forecast_3h": "forecast_3h",
}


def connect(lake_dir: Path):
    import duckdb

    connection = duckdb.connect()
    registered = []
    for table, folder in TABLES.items():
        folder_path = lake_dir / "curated" / folder
        if not any(folder_path.rglob("*.parquet")):
            continue
        pattern = (folder_path.as_posix() + "/**/*.parquet").replace("'", "''")
        # union_by_name: files written by older schema versions simply miss the newer columns.
        connection.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{pattern}', union_by_name=true, hive_partitioning=false)")
        registered.append(table)
    return connection, registered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consulta as tabelas Parquet locais com DuckDB (mesmo SQL do Athena).")
    parser.add_argument("file", nargs="?", help="Arquivo .sql (por exemplo queries/monthly_from_daily.sql)")
    parser.add_argument("--sql", help="Consulta SQL inline")
    parser.add_argument("--lake-dir", default=".local-data/lake")
    parser.add_argument("--output", help="Salva o resultado em .csv ou .parquet em vez de imprimir")
    parser.add_argument("--limit", type=int, default=50, help="Linhas exibidas no terminal (padrao 50)")
    args = parser.parse_args(argv)

    if not args.file and not args.sql:
        parser.error("informe um arquivo .sql ou --sql")
    sql = args.sql or (ROOT / args.file if not Path(args.file).is_absolute() else Path(args.file)).read_text(encoding="utf-8")
    connection, registered = connect(ROOT / args.lake_dir)
    if not registered:
        print(f"Nenhum Parquet encontrado em {args.lake_dir}/curated. Rode o servico offline ou scripts/export-from-aws.ps1.", file=sys.stderr)
        return 2
    relation = connection.sql(sql.strip().rstrip(";"))
    if args.output:
        output = Path(args.output)
        if output.suffix.lower() == ".parquet":
            relation.write_parquet(str(output))
        else:
            relation.write_csv(str(output))
        print(f"{relation.shape[0]} linhas gravadas em {output}")
        return 0
    relation.show(max_rows=args.limit, max_width=200)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
