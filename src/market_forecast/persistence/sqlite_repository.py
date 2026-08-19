"""SQLite repository for raw artifacts and normalized market prices."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from market_forecast.domain import HourlyMarketPrice
from market_forecast.persistence.raw_artifacts import StoredArtifact


class SQLiteMarketRepository:
    """Own the transactional SQLite contract for collected market data."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create the database and schema when missing."""

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS raw_artifacts (
                    id INTEGER PRIMARY KEY,
                    sha256 TEXT NOT NULL,
                    source TEXT NOT NULL,
                    delivery_date TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    byte_count INTEGER NOT NULL CHECK (byte_count > 0),
                    fetched_at_utc TEXT NOT NULL,
                    validation_status TEXT NOT NULL,
                    UNIQUE (source, delivery_date, sha256)
                );

                CREATE TABLE IF NOT EXISTS market_prices (
                    id INTEGER PRIMARY KEY,
                    delivery_start_utc TEXT NOT NULL,
                    delivery_end_utc TEXT NOT NULL,
                    settlement_period INTEGER NOT NULL CHECK (settlement_period > 0),
                    price TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    bidding_zone TEXT NOT NULL,
                    market TEXT NOT NULL,
                    source TEXT NOT NULL,
                    volume_mwh TEXT,
                    source_revision TEXT,
                    raw_artifact_id INTEGER NOT NULL REFERENCES raw_artifacts(id),
                    ingested_at_utc TEXT NOT NULL,
                    UNIQUE (source, market, bidding_zone, delivery_start_utc)
                );

                CREATE INDEX IF NOT EXISTS idx_market_prices_delivery
                ON market_prices (delivery_start_utc, bidding_zone, market);

                CREATE TABLE IF NOT EXISTS collection_attempts (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL,
                    delivery_date TEXT NOT NULL,
                    attempted_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('collected', 'unpublished', 'failed')),
                    inserted_records INTEGER NOT NULL DEFAULT 0 CHECK (inserted_records >= 0),
                    message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_collection_attempts_latest
                ON collection_attempts (source, attempted_at_utc DESC);

                CREATE TABLE IF NOT EXISTS forecast_runs (
                    id INTEGER PRIMARY KEY,
                    target_delivery_date TEXT NOT NULL,
                    issued_at_utc TEXT NOT NULL,
                    training_cutoff_date TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    backtest_days INTEGER NOT NULL CHECK (backtest_days > 0),
                    backtest_observations INTEGER NOT NULL CHECK (backtest_observations > 0),
                    mae TEXT NOT NULL,
                    rmse TEXT NOT NULL,
                    absolute_error_p80 TEXT NOT NULL,
                    UNIQUE (target_delivery_date, model_name, model_version)
                );

                CREATE TABLE IF NOT EXISTS forecast_points (
                    id INTEGER PRIMARY KEY,
                    forecast_run_id INTEGER NOT NULL REFERENCES forecast_runs(id),
                    delivery_start_utc TEXT NOT NULL,
                    predicted_price TEXT NOT NULL,
                    interval_low TEXT NOT NULL,
                    interval_high TEXT NOT NULL,
                    method TEXT NOT NULL,
                    sample_count INTEGER NOT NULL CHECK (sample_count > 0),
                    UNIQUE (forecast_run_id, delivery_start_utc)
                );
                """
            )

    def store_collection(
        self,
        artifact: StoredArtifact,
        source: str,
        delivery_date: date,
        source_url: str,
        content_type: str,
        fetched_at_utc: datetime,
        prices: Iterable[HourlyMarketPrice],
        validation_status: str,
    ) -> tuple[int, int]:
        """Store an artifact and idempotently insert its normalized price rows."""

        fetched_at = _utc_iso(fetched_at_utc, "fetched_at_utc")
        if validation_status not in {"validated", "raw_only"}:
            raise ValueError("Unsupported validation_status")
        rows = list(prices)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO raw_artifacts (
                    sha256, source, delivery_date, source_url, content_type,
                    local_path, byte_count, fetched_at_utc, validation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, delivery_date, sha256) DO UPDATE SET
                    validation_status = CASE
                        WHEN raw_artifacts.validation_status = 'validated'
                        THEN raw_artifacts.validation_status
                        ELSE excluded.validation_status
                    END
                """,
                (
                    artifact.sha256,
                    source,
                    delivery_date.isoformat(),
                    source_url,
                    content_type,
                    str(artifact.path),
                    artifact.byte_count,
                    fetched_at,
                    validation_status,
                ),
            )
            artifact_row = connection.execute(
                """SELECT id FROM raw_artifacts
                   WHERE source = ? AND delivery_date = ? AND sha256 = ?""",
                (source, delivery_date.isoformat(), artifact.sha256),
            ).fetchone()
            if artifact_row is None:
                raise RuntimeError("Raw artifact could not be persisted")
            artifact_id = int(artifact_row[0])

            inserted = 0
            for item in rows:
                cursor = connection.execute(
                    """
                    INSERT INTO market_prices (
                        delivery_start_utc, delivery_end_utc, settlement_period,
                        price, currency, bidding_zone, market, source, volume_mwh,
                        source_revision, raw_artifact_id, ingested_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, market, bidding_zone, delivery_start_utc)
                    DO NOTHING
                    """,
                    (
                        _utc_iso(item.delivery_start_utc, "delivery_start_utc"),
                        _utc_iso(item.delivery_end_utc, "delivery_end_utc"),
                        item.settlement_period,
                        str(item.price),
                        item.currency,
                        item.bidding_zone,
                        item.market,
                        item.source,
                        str(item.volume_mwh) if item.volume_mwh is not None else None,
                        item.source_revision,
                        artifact_id,
                        fetched_at,
                    ),
                )
                inserted += cursor.rowcount
                if cursor.rowcount == 0:
                    existing = connection.execute(
                        """SELECT delivery_end_utc, settlement_period, price, currency,
                                  volume_mwh, source_revision
                           FROM market_prices
                           WHERE source = ? AND market = ? AND bidding_zone = ?
                             AND delivery_start_utc = ?""",
                        (
                            item.source,
                            item.market,
                            item.bidding_zone,
                            _utc_iso(item.delivery_start_utc, "delivery_start_utc"),
                        ),
                    ).fetchone()
                    expected = (
                        _utc_iso(item.delivery_end_utc, "delivery_end_utc"),
                        item.settlement_period,
                        str(item.price),
                        item.currency,
                        str(item.volume_mwh) if item.volume_mwh is not None else None,
                        item.source_revision,
                    )
                    if existing != expected:
                        raise ValueError(
                            "Conflicting market price already exists for the same source interval"
                        )
        return artifact_id, inserted

    def count_prices(self) -> int:
        """Return the current normalized price row count."""

        with closing(self._connect()) as connection:
            row = connection.execute("SELECT COUNT(*) FROM market_prices").fetchone()
        return int(row[0]) if row else 0

    def list_prices(
        self,
        source: str,
        period_start_utc: datetime,
        period_end_utc: datetime,
        bidding_zone: str | None = None,
    ) -> list[tuple[datetime, Decimal]]:
        """Return ordered price values inside one explicit UTC interval."""

        start = _utc_iso(period_start_utc, "period_start_utc")
        end = _utc_iso(period_end_utc, "period_end_utc")
        with closing(self._connect()) as connection:
            query = """SELECT delivery_start_utc, price
                       FROM market_prices
                       WHERE source = ? AND delivery_start_utc >= ?
                         AND delivery_start_utc < ?"""
            parameters: list[str] = [source, start, end]
            if bidding_zone is not None:
                query += " AND bidding_zone = ?"
                parameters.append(bidding_zone)
            query += " ORDER BY delivery_start_utc"
            rows = connection.execute(query, parameters).fetchall()
        return [(_parse_utc(row[0]), Decimal(row[1])) for row in rows]

    def available_period(
        self, source: str, bidding_zone: str | None = None
    ) -> tuple[datetime, datetime] | None:
        """Return the earliest and latest stored delivery timestamps for a source."""

        with closing(self._connect()) as connection:
            query = """SELECT MIN(delivery_start_utc), MAX(delivery_start_utc)
                       FROM market_prices WHERE source = ?"""
            parameters = [source]
            if bidding_zone is not None:
                query += " AND bidding_zone = ?"
                parameters.append(bidding_zone)
            row = connection.execute(query, parameters).fetchone()
        if row is None or row[0] is None or row[1] is None:
            return None
        return _parse_utc(row[0]), _parse_utc(row[1])

    def record_collection_attempt(
        self,
        source: str,
        delivery_date: date,
        attempted_at_utc: datetime,
        status: str,
        inserted_records: int = 0,
        message: str | None = None,
    ) -> None:
        """Persist one scheduler outcome for freshness reporting and diagnostics."""

        if status not in {"collected", "unpublished", "failed"}:
            raise ValueError("Unsupported collection attempt status")
        if inserted_records < 0:
            raise ValueError("inserted_records must not be negative")
        attempted_at = _utc_iso(attempted_at_utc, "attempted_at_utc")
        self.initialize()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO collection_attempts (
                       source, delivery_date, attempted_at_utc, status,
                       inserted_records, message
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    source,
                    delivery_date.isoformat(),
                    attempted_at,
                    status,
                    inserted_records,
                    message,
                ),
            )

    def latest_collection_attempt(
        self, source: str
    ) -> tuple[date, datetime, str, int, str | None] | None:
        """Return the newest scheduler outcome for a source."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT delivery_date, attempted_at_utc, status,
                          inserted_records, message
                   FROM collection_attempts
                   WHERE source = ?
                   ORDER BY attempted_at_utc DESC, id DESC
                   LIMIT 1""",
                (source,),
            ).fetchone()
        if row is None:
            return None
        return date.fromisoformat(row[0]), _parse_utc(row[1]), row[2], int(row[3]), row[4]

    def store_forecast_snapshot(
        self,
        *,
        target_delivery_date: date,
        issued_at_utc: datetime,
        training_cutoff_date: date,
        model_name: str,
        model_version: str,
        backtest_days: int,
        backtest_observations: int,
        mae: Decimal,
        rmse: Decimal,
        absolute_error_p80: Decimal,
        points: Iterable[tuple[datetime, Decimal, Decimal, Decimal, str, int]],
    ) -> tuple[int, bool]:
        """Insert one immutable forecast vintage, returning its id and creation flag."""

        issued_at = _utc_iso(issued_at_utc, "issued_at_utc")
        point_rows = list(points)
        if not point_rows:
            raise ValueError("Forecast snapshot must contain points")
        self.initialize()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """INSERT INTO forecast_runs (
                       target_delivery_date, issued_at_utc, training_cutoff_date,
                       model_name, model_version, backtest_days,
                       backtest_observations, mae, rmse, absolute_error_p80
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(target_delivery_date, model_name, model_version)
                   DO NOTHING""",
                (
                    target_delivery_date.isoformat(),
                    issued_at,
                    training_cutoff_date.isoformat(),
                    model_name,
                    model_version,
                    backtest_days,
                    backtest_observations,
                    str(mae),
                    str(rmse),
                    str(absolute_error_p80),
                ),
            )
            created = cursor.rowcount == 1
            run_row = connection.execute(
                """SELECT id FROM forecast_runs
                   WHERE target_delivery_date = ? AND model_name = ? AND model_version = ?""",
                (target_delivery_date.isoformat(), model_name, model_version),
            ).fetchone()
            if run_row is None:
                raise RuntimeError("Forecast run could not be persisted")
            run_id = int(run_row[0])
            if created:
                for timestamp, predicted, low, high, method, sample_count in point_rows:
                    connection.execute(
                        """INSERT INTO forecast_points (
                               forecast_run_id, delivery_start_utc, predicted_price,
                               interval_low, interval_high, method, sample_count
                           ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            run_id,
                            _utc_iso(timestamp, "delivery_start_utc"),
                            str(predicted),
                            str(low),
                            str(high),
                            method,
                            sample_count,
                        ),
                    )
            else:
                stored = connection.execute(
                    """SELECT delivery_start_utc, predicted_price, interval_low,
                              interval_high, method, sample_count
                       FROM forecast_points WHERE forecast_run_id = ?
                       ORDER BY delivery_start_utc""",
                    (run_id,),
                ).fetchall()
                expected = sorted(
                    (
                        _utc_iso(timestamp, "delivery_start_utc"),
                        str(predicted),
                        str(low),
                        str(high),
                        method,
                        sample_count,
                    )
                    for timestamp, predicted, low, high, method, sample_count in point_rows
                )
                if stored != expected:
                    raise ValueError("Conflicting immutable forecast snapshot already exists")
        return run_id, created

    def list_forecast_runs(
        self, limit: int = 30
    ) -> list[tuple[int, date, datetime, date, str, str, int, int, Decimal, Decimal, Decimal]]:
        """Return newest immutable forecast vintages for monitoring."""

        if limit <= 0:
            raise ValueError("limit must be positive")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT id, target_delivery_date, issued_at_utc,
                          training_cutoff_date, model_name, model_version,
                          backtest_days, backtest_observations, mae, rmse,
                          absolute_error_p80
                   FROM forecast_runs
                   ORDER BY target_delivery_date DESC, issued_at_utc DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            (
                int(row[0]),
                date.fromisoformat(row[1]),
                _parse_utc(row[2]),
                date.fromisoformat(row[3]),
                row[4],
                row[5],
                int(row[6]),
                int(row[7]),
                Decimal(row[8]),
                Decimal(row[9]),
                Decimal(row[10]),
            )
            for row in rows
        ]

    def list_forecast_points(
        self, forecast_run_id: int
    ) -> list[tuple[datetime, Decimal, Decimal, Decimal, str, int]]:
        """Return ordered points for one immutable forecast vintage."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT delivery_start_utc, predicted_price, interval_low,
                          interval_high, method, sample_count
                   FROM forecast_points
                   WHERE forecast_run_id = ?
                   ORDER BY delivery_start_utc""",
                (forecast_run_id,),
            ).fetchall()
        return [
            (
                _parse_utc(row[0]),
                Decimal(row[1]),
                Decimal(row[2]),
                Decimal(row[3]),
                row[4],
                int(row[5]),
            )
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _utc_iso(value: datetime, name: str) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError(f"{name} must use UTC")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)
