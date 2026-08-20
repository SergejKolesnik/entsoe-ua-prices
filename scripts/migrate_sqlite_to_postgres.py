"""One-time, guarded migration from the local SQLite database to PostgreSQL."""

from __future__ import annotations

import argparse
import getpass
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Iterable

import psycopg
from psycopg import sql


TABLE_COLUMNS = {
    "raw_artifacts": (
        "id", "sha256", "source", "delivery_date", "source_url", "content_type",
        "local_path", "byte_count", "fetched_at_utc", "validation_status",
    ),
    "market_prices": (
        "id", "delivery_start_utc", "delivery_end_utc", "settlement_period", "price",
        "currency", "bidding_zone", "market", "source", "volume_mwh",
        "source_revision", "raw_artifact_id", "ingested_at_utc",
    ),
    "exchange_rates": (
        "effective_date", "currency", "rate_uah_per_unit", "source", "fetched_at_utc",
    ),
    "cross_border_flows": (
        "id", "delivery_start_utc", "delivery_end_utc", "source_zone", "target_zone",
        "power_mw", "source", "source_revision", "ingested_at_utc",
    ),
    "collection_attempts": (
        "id", "source", "delivery_date", "attempted_at_utc", "status",
        "inserted_records", "message",
    ),
    "forecast_runs": (
        "id", "target_delivery_date", "issued_at_utc", "training_cutoff_date",
        "model_name", "model_version", "backtest_days", "backtest_observations",
        "mae", "rmse", "absolute_error_p80",
    ),
    "forecast_points": (
        "id", "forecast_run_id", "delivery_start_utc", "predicted_price",
        "interval_low", "interval_high", "method", "sample_count",
    ),
}


def build_parser() -> argparse.ArgumentParser:
    """Create the guarded migration command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=Path("data/market_forecast.sqlite3"),
        help="Source SQLite database.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration. Without this flag only local counts are shown.",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Plan or execute the one-time migration without exposing credentials."""

    args = build_parser().parse_args(argv)
    if args.batch_size <= 0:
        raise ValueError("batch-size must be positive")
    if not args.sqlite.is_file():
        raise FileNotFoundError(f"SQLite database not found: {args.sqlite}")

    with closing(sqlite3.connect(args.sqlite)) as source:
        _verify_sqlite_integrity(source)
        source_counts = _table_counts(source)
        _print_counts("SQLite source", source_counts)
        if not args.apply:
            print("Plan only: no data was written.")
            return 0

        database_url = os.getenv("DATABASE_URL") or getpass.getpass(
            "Neon connection string (input hidden): "
        )
        if not database_url:
            raise RuntimeError("A Neon connection string is required when --apply is used")
        with psycopg.connect(database_url) as target:
            target_counts = _postgres_counts(target)
            if any(target_counts.values()):
                raise RuntimeError("Neon destination is not empty; migration was refused")
            for table, columns in TABLE_COLUMNS.items():
                _copy_table(source, target, table, columns, args.batch_size)
            _reset_identity_sequences(target)
            migrated_counts = _postgres_counts(target)
            if migrated_counts != source_counts:
                raise RuntimeError("Post-migration row counts do not match; transaction rolled back")
            _verify_postgres_relationships(target)
            _print_counts("Neon destination", migrated_counts)
        print("Migration completed and verified.")
    return 0


def _verify_sqlite_integrity(connection: sqlite3.Connection) -> None:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()
    if integrity != ("ok",):
        raise RuntimeError("SQLite integrity check failed")
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise RuntimeError("SQLite foreign-key check failed")


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        for table in TABLE_COLUMNS
    }


def _postgres_counts(connection: psycopg.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in TABLE_COLUMNS:
        query = sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
        counts[table] = int(connection.execute(query).fetchone()[0])
    return counts


def _copy_table(
    source: sqlite3.Connection,
    target: psycopg.Connection,
    table: str,
    columns: tuple[str, ...],
    batch_size: int,
) -> None:
    column_list = ", ".join(f'"{column}"' for column in columns)
    source_cursor = source.execute(f'SELECT {column_list} FROM "{table}" ORDER BY rowid')
    insert = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    while rows := source_cursor.fetchmany(batch_size):
        with target.cursor() as target_cursor:
            target_cursor.executemany(insert, rows)


def _reset_identity_sequences(connection: psycopg.Connection) -> None:
    for table in TABLE_COLUMNS:
        if "id" not in TABLE_COLUMNS[table]:
            continue
        statement = sql.SQL(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
            "COALESCE((SELECT MAX(id) FROM {}), 1), "
            "EXISTS (SELECT 1 FROM {}))"
        ).format(sql.Identifier(table), sql.Identifier(table))
        connection.execute(statement, (table,))


def _verify_postgres_relationships(connection: psycopg.Connection) -> None:
    checks: Iterable[tuple[str, str]] = (
        (
            "market_prices without artifacts",
            "SELECT COUNT(*) FROM market_prices p LEFT JOIN raw_artifacts a "
            "ON a.id = p.raw_artifact_id WHERE a.id IS NULL",
        ),
        (
            "forecast points without runs",
            "SELECT COUNT(*) FROM forecast_points p LEFT JOIN forecast_runs r "
            "ON r.id = p.forecast_run_id WHERE r.id IS NULL",
        ),
    )
    for label, query in checks:
        if int(connection.execute(query).fetchone()[0]):
            raise RuntimeError(f"Post-migration relationship check failed: {label}")


def _print_counts(label: str, counts: dict[str, int]) -> None:
    print(label)
    for table, count in counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    raise SystemExit(main())
