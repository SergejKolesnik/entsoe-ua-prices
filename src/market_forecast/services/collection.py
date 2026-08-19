"""One-shot market data collection workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from market_forecast.parsers import parse_operator_market_workbook, parse_price_document
from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository
from market_forecast.sources import EntsoeSource, OperatorMarketSource
from market_forecast.validation import validate_delivery_periods


@dataclass(frozen=True, slots=True)
class CollectionResult:
    """Summary of a completed idempotent collection operation."""

    source: str
    delivery_date: date
    artifact_sha256: str
    parsed_records: int
    inserted_records: int


class MarketCollectionService:
    """Coordinate raw landing, parsing, validation, and transactional storage."""

    def __init__(
        self,
        repository: SQLiteMarketRepository,
        artifact_store: RawArtifactStore,
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store

    def collect_entsoe(
        self,
        delivery_date: date,
        source: EntsoeSource,
        bidding_zone_eic: str,
    ) -> CollectionResult:
        """Collect and persist one Kyiv delivery day from ENTSO-E."""

        kyiv = ZoneInfo("Europe/Kyiv")
        period_start = datetime.combine(delivery_date, time.min, kyiv).astimezone(timezone.utc)
        period_end = datetime.combine(
            delivery_date + timedelta(days=1), time.min, kyiv
        ).astimezone(timezone.utc)
        raw = source.fetch_day_ahead_prices(period_start, period_end, bidding_zone_eic)
        records = parse_price_document(raw.content)
        validate_delivery_periods(records)
        if (
            records[0].delivery_start_utc != period_start
            or records[-1].delivery_end_utc != period_end
        ):
            raise ValueError("ENTSO-E prices do not cover the requested delivery day")
        artifact = self.artifact_store.save(raw.content, "entsoe", delivery_date, "xml")
        self.repository.initialize()
        _, inserted = self.repository.store_collection(
            artifact=artifact,
            source="entsoe",
            delivery_date=delivery_date,
            source_url=raw.source_url,
            content_type=raw.content_type,
            fetched_at_utc=datetime.now(timezone.utc),
            prices=records,
            validation_status="validated",
        )
        return CollectionResult("entsoe", delivery_date, artifact.sha256, len(records), inserted)

    def collect_operator_artifact(
        self,
        delivery_date: date,
        source: OperatorMarketSource,
    ) -> CollectionResult | None:
        """Land an official operator workbook without interpreting unknown columns."""

        observation = source.discover(delivery_date)
        if observation is None:
            return None
        raw = source.download(observation)
        extension = "xlsx" if raw.content.startswith(b"PK\x03\x04") else "xls"
        artifact = self.artifact_store.save(
            raw.content, "operator_market", delivery_date, extension
        )
        records = parse_operator_market_workbook(raw.content, delivery_date)
        validate_delivery_periods(records, expected_periods=len(records))
        self.repository.initialize()
        _, inserted = self.repository.store_collection(
            artifact=artifact,
            source="operator_market",
            delivery_date=delivery_date,
            source_url=raw.source_url,
            content_type=raw.content_type,
            fetched_at_utc=datetime.now(timezone.utc),
            prices=records,
            validation_status="validated",
        )
        return CollectionResult(
            "operator_market", delivery_date, artifact.sha256, len(records), inserted
        )
