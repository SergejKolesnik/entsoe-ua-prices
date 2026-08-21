"""SQLite repository for raw artifacts and normalized market prices."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from market_forecast.domain import CrossBorderFlow, HourlyMarketPrice, WeatherForecastPoint
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

                CREATE TABLE IF NOT EXISTS exchange_rates (
                    effective_date TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    rate_uah_per_unit TEXT NOT NULL,
                    source TEXT NOT NULL,
                    fetched_at_utc TEXT NOT NULL,
                    PRIMARY KEY (effective_date, currency, source)
                );

                CREATE TABLE IF NOT EXISTS cross_border_flows (
                    id INTEGER PRIMARY KEY,
                    delivery_start_utc TEXT NOT NULL,
                    delivery_end_utc TEXT NOT NULL,
                    source_zone TEXT NOT NULL,
                    target_zone TEXT NOT NULL,
                    power_mw TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_revision TEXT,
                    ingested_at_utc TEXT NOT NULL,
                    UNIQUE (source, source_zone, target_zone, delivery_start_utc)
                );

                CREATE INDEX IF NOT EXISTS idx_cross_border_flows_delivery
                ON cross_border_flows (delivery_start_utc, source_zone, target_zone);

                CREATE TABLE IF NOT EXISTS weather_forecasts (
                    source TEXT NOT NULL,
                    model TEXT NOT NULL,
                    location_id TEXT NOT NULL,
                    latitude TEXT NOT NULL,
                    longitude TEXT NOT NULL,
                    forecast_vintage_utc TEXT NOT NULL,
                    valid_start_utc TEXT NOT NULL,
                    temperature_c TEXT NOT NULL,
                    cloud_cover_percent TEXT NOT NULL,
                    shortwave_radiation_wm2 TEXT NOT NULL,
                    wind_speed_100m_kmh TEXT NOT NULL,
                    raw_artifact_id INTEGER NOT NULL REFERENCES raw_artifacts(id),
                    ingested_at_utc TEXT NOT NULL,
                    PRIMARY KEY (
                        source, model, location_id,
                        forecast_vintage_utc, valid_start_utc
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_weather_forecasts_valid
                ON weather_forecasts (valid_start_utc, forecast_vintage_utc);

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
                    if existing != expected and existing[:4] == expected[:4] and existing[4] is None:
                        connection.execute(
                            """UPDATE market_prices
                               SET volume_mwh = ?, source_revision = COALESCE(?, source_revision)
                               WHERE source = ? AND market = ? AND bidding_zone = ?
                                 AND delivery_start_utc = ?""",
                            (
                                expected[4], expected[5], item.source, item.market,
                                item.bidding_zone,
                                _utc_iso(item.delivery_start_utc, "delivery_start_utc"),
                            ),
                        )
                    elif existing != expected:
                        raise ValueError(
                            "Conflicting market price already exists for the same source interval"
                        )
        return artifact_id, inserted

    def store_exchange_rates(
        self, rates: dict[date, Decimal], fetched_at_utc: datetime
    ) -> int:
        """Upsert official NBU EUR rates without changing market-price rows."""

        fetched_at = _utc_iso(fetched_at_utc, "fetched_at_utc")
        self.initialize()
        changed = 0
        with closing(self._connect()) as connection, connection:
            for effective_date, rate in rates.items():
                cursor = connection.execute(
                    """INSERT INTO exchange_rates (
                           effective_date, currency, rate_uah_per_unit, source, fetched_at_utc
                       ) VALUES (?, 'EUR', ?, 'nbu', ?)
                       ON CONFLICT(effective_date, currency, source) DO UPDATE SET
                           rate_uah_per_unit = excluded.rate_uah_per_unit,
                           fetched_at_utc = excluded.fetched_at_utc""",
                    (effective_date.isoformat(), str(rate), fetched_at),
                )
                changed += cursor.rowcount
        return changed

    def list_exchange_rates(self, date_from: date, date_to: date) -> dict[date, Decimal]:
        """Return stored official EUR rates for an inclusive range."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT effective_date, rate_uah_per_unit FROM exchange_rates
                   WHERE currency = 'EUR' AND source = 'nbu'
                     AND effective_date >= ? AND effective_date <= ?
                   ORDER BY effective_date""",
                (date_from.isoformat(), date_to.isoformat()),
            ).fetchall()
        return {date.fromisoformat(row[0]): Decimal(row[1]) for row in rows}

    def store_flows(self, flows: Iterable[CrossBorderFlow], fetched_at_utc: datetime) -> int:
        """Idempotently persist normalized ENTSO-E physical flows."""

        fetched_at = _utc_iso(fetched_at_utc, "fetched_at_utc")
        self.initialize()
        inserted = 0
        with closing(self._connect()) as connection, connection:
            for flow in flows:
                cursor = connection.execute(
                    """INSERT INTO cross_border_flows (
                           delivery_start_utc, delivery_end_utc, source_zone,
                           target_zone, power_mw, source, source_revision, ingested_at_utc
                       ) VALUES (?, ?, ?, ?, ?, 'entsoe', ?, ?)
                       ON CONFLICT(source, source_zone, target_zone, delivery_start_utc)
                       DO UPDATE SET power_mw = excluded.power_mw,
                                     delivery_end_utc = excluded.delivery_end_utc,
                                     source_revision = excluded.source_revision,
                                     ingested_at_utc = excluded.ingested_at_utc""",
                    (
                        _utc_iso(flow.delivery_start_utc, "delivery_start_utc"),
                        _utc_iso(flow.delivery_end_utc, "delivery_end_utc"),
                        flow.source_zone, flow.target_zone, str(flow.power_mw),
                        flow.source_revision, fetched_at,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def list_flows(
        self, period_start_utc: datetime, period_end_utc: datetime
    ) -> list[tuple[datetime, datetime, str, str, Decimal]]:
        """Return physical flows inside one UTC interval."""

        start = _utc_iso(period_start_utc, "period_start_utc")
        end = _utc_iso(period_end_utc, "period_end_utc")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT delivery_start_utc, delivery_end_utc,
                          source_zone, target_zone, power_mw
                   FROM cross_border_flows
                   WHERE delivery_start_utc >= ? AND delivery_start_utc < ?
                   ORDER BY delivery_start_utc, source_zone, target_zone""",
                (start, end),
            ).fetchall()
        return [
            (_parse_utc(row[0]), _parse_utc(row[1]), row[2], row[3], Decimal(row[4]))
            for row in rows
        ]

    def store_weather_forecast(
        self,
        artifact: StoredArtifact,
        source_url: str,
        fetched_at_utc: datetime,
        points: Iterable[WeatherForecastPoint],
    ) -> int:
        """Persist an immutable regional forecast vintage and its raw JSON."""

        rows = list(points)
        if not rows:
            raise ValueError("Weather forecast must contain points")
        fetched_at = _utc_iso(fetched_at_utc, "fetched_at_utc")
        delivery_date = min(point.valid_start_utc for point in rows).date()
        self.initialize()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO raw_artifacts (
                       sha256, source, delivery_date, source_url, content_type,
                       local_path, byte_count, fetched_at_utc, validation_status
                   ) VALUES (?, 'open_meteo', ?, ?, 'application/json', ?, ?, ?, 'validated')
                   ON CONFLICT(source, delivery_date, sha256) DO NOTHING""",
                (
                    artifact.sha256,
                    delivery_date.isoformat(),
                    source_url,
                    str(artifact.path),
                    artifact.byte_count,
                    fetched_at,
                ),
            )
            artifact_row = connection.execute(
                """SELECT id FROM raw_artifacts
                   WHERE source = 'open_meteo' AND delivery_date = ? AND sha256 = ?""",
                (delivery_date.isoformat(), artifact.sha256),
            ).fetchone()
            if artifact_row is None:
                raise RuntimeError("Weather raw artifact could not be persisted")
            inserted = 0
            for point in rows:
                cursor = connection.execute(
                    """INSERT INTO weather_forecasts (
                           source, model, location_id, latitude, longitude,
                           forecast_vintage_utc, valid_start_utc, temperature_c,
                           cloud_cover_percent, shortwave_radiation_wm2,
                           wind_speed_100m_kmh, raw_artifact_id, ingested_at_utc
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(source, model, location_id,
                                   forecast_vintage_utc, valid_start_utc)
                       DO NOTHING""",
                    (
                        point.source, point.model, point.location_id,
                        str(point.latitude), str(point.longitude),
                        _utc_iso(point.forecast_vintage_utc, "forecast_vintage_utc"),
                        _utc_iso(point.valid_start_utc, "valid_start_utc"),
                        str(point.temperature_c), str(point.cloud_cover_percent),
                        str(point.shortwave_radiation_wm2),
                        str(point.wind_speed_100m_kmh), int(artifact_row[0]), fetched_at,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def list_weather_forecasts(
        self,
        period_start_utc: datetime,
        period_end_utc: datetime,
        forecast_vintage_utc: datetime | None = None,
    ) -> list[WeatherForecastPoint]:
        """Return one explicit vintage or the newest vintage for each valid hour."""

        start = _utc_iso(period_start_utc, "period_start_utc")
        end = _utc_iso(period_end_utc, "period_end_utc")
        with closing(self._connect()) as connection:
            if forecast_vintage_utc is not None:
                rows = connection.execute(
                    """SELECT location_id, latitude, longitude, forecast_vintage_utc,
                              valid_start_utc, temperature_c, cloud_cover_percent,
                              shortwave_radiation_wm2, wind_speed_100m_kmh, source, model
                       FROM weather_forecasts
                       WHERE valid_start_utc >= ? AND valid_start_utc < ?
                         AND forecast_vintage_utc = ?
                       ORDER BY location_id, valid_start_utc""",
                    (start, end, _utc_iso(forecast_vintage_utc, "forecast_vintage_utc")),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT location_id, latitude, longitude, forecast_vintage_utc,
                              valid_start_utc, temperature_c, cloud_cover_percent,
                              shortwave_radiation_wm2, wind_speed_100m_kmh, source, model
                       FROM (
                           SELECT *, ROW_NUMBER() OVER (
                               PARTITION BY source, model, location_id, valid_start_utc
                               ORDER BY forecast_vintage_utc DESC
                           ) AS position
                           FROM weather_forecasts
                           WHERE valid_start_utc >= ? AND valid_start_utc < ?
                       ) WHERE position = 1
                       ORDER BY location_id, valid_start_utc""",
                    (start, end),
                ).fetchall()
        return [
            WeatherForecastPoint(
                location_id=row[0], latitude=Decimal(row[1]), longitude=Decimal(row[2]),
                forecast_vintage_utc=_parse_utc(row[3]), valid_start_utc=_parse_utc(row[4]),
                temperature_c=Decimal(row[5]), cloud_cover_percent=Decimal(row[6]),
                shortwave_radiation_wm2=Decimal(row[7]),
                wind_speed_100m_kmh=Decimal(row[8]), source=row[9], model=row[10],
            )
            for row in rows
        ]

    def list_price_volumes(
        self, source: str, period_start_utc: datetime, period_end_utc: datetime
    ) -> list[tuple[datetime, Decimal | None]]:
        """Return ordered accepted market volumes alongside timestamps."""

        start = _utc_iso(period_start_utc, "period_start_utc")
        end = _utc_iso(period_end_utc, "period_end_utc")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT delivery_start_utc, volume_mwh FROM market_prices
                   WHERE source = ? AND delivery_start_utc >= ? AND delivery_start_utc < ?
                   ORDER BY delivery_start_utc""",
                (source, start, end),
            ).fetchall()
        return [(_parse_utc(row[0]), Decimal(row[1]) if row[1] is not None else None) for row in rows]

    def list_latest_artifact_paths(self, source: str) -> list[tuple[date, Path]]:
        """Return the newest validated raw artifact path for each delivery day."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT artifact.delivery_date, artifact.local_path
                   FROM raw_artifacts AS artifact
                   JOIN (
                       SELECT delivery_date, MAX(id) AS latest_id
                       FROM raw_artifacts
                       WHERE source = ? AND validation_status = 'validated'
                       GROUP BY delivery_date
                   ) AS latest ON latest.latest_id = artifact.id
                   ORDER BY artifact.delivery_date""",
                (source,),
            ).fetchall()
        return [(date.fromisoformat(row[0]), Path(row[1])) for row in rows]

    def enrich_price_volumes(self, prices: Iterable[HourlyMarketPrice]) -> int:
        """Fill missing volumes only when the stored price identity still matches."""

        updated = 0
        with closing(self._connect()) as connection, connection:
            for item in prices:
                if item.volume_mwh is None:
                    continue
                row = connection.execute(
                    """SELECT price, currency, volume_mwh FROM market_prices
                       WHERE source = ? AND market = ? AND bidding_zone = ?
                         AND delivery_start_utc = ?""",
                    (
                        item.source, item.market, item.bidding_zone,
                        _utc_iso(item.delivery_start_utc, "delivery_start_utc"),
                    ),
                ).fetchone()
                if row is None:
                    raise ValueError("Cannot enrich volume without a stored market price")
                if Decimal(row[0]) != item.price or row[1] != item.currency:
                    raise ValueError("Cannot enrich volume for a conflicting market price")
                if row[2] is None:
                    cursor = connection.execute(
                        """UPDATE market_prices SET volume_mwh = ?
                           WHERE source = ? AND market = ? AND bidding_zone = ?
                             AND delivery_start_utc = ? AND volume_mwh IS NULL""",
                        (
                            str(item.volume_mwh), item.source, item.market,
                            item.bidding_zone,
                            _utc_iso(item.delivery_start_utc, "delivery_start_utc"),
                        ),
                    )
                    updated += cursor.rowcount
                elif Decimal(row[2]) != item.volume_mwh:
                    raise ValueError("Stored market volume conflicts with the official artifact")
        return updated

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

    def latest_collection_attempts(
        self, sources: Iterable[str]
    ) -> dict[str, tuple[date, datetime, str, int, str | None]]:
        """Return the newest scheduler outcome for each requested source."""

        source_list = list(dict.fromkeys(sources))
        if not source_list:
            return {}
        placeholders = ", ".join("?" for _ in source_list)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""SELECT source, delivery_date, attempted_at_utc, status,
                           inserted_records, message
                    FROM (
                        SELECT source, delivery_date, attempted_at_utc, status,
                               inserted_records, message,
                               ROW_NUMBER() OVER (
                                   PARTITION BY source
                                   ORDER BY attempted_at_utc DESC, id DESC
                               ) AS position
                        FROM collection_attempts
                        WHERE source IN ({placeholders})
                    )
                    WHERE position = 1""",
                source_list,
            ).fetchall()
        return {
            row[0]: (
                date.fromisoformat(row[1]),
                _parse_utc(row[2]),
                row[3],
                int(row[4]),
                row[5],
            )
            for row in rows
        }

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
