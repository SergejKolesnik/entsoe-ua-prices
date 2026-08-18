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
    ) -> list[tuple[datetime, Decimal]]:
        """Return ordered price values inside one explicit UTC interval."""

        start = _utc_iso(period_start_utc, "period_start_utc")
        end = _utc_iso(period_end_utc, "period_end_utc")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT delivery_start_utc, price
                   FROM market_prices
                   WHERE source = ? AND delivery_start_utc >= ?
                     AND delivery_start_utc < ?
                   ORDER BY delivery_start_utc""",
                (source, start, end),
            ).fetchall()
        return [(_parse_utc(row[0]), Decimal(row[1])) for row in rows]

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
