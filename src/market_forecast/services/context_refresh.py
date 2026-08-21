"""Daily refresh of supporting market context with isolated outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from market_forecast.config import Settings
from market_forecast.neighbor_markets import NEIGHBOR_MARKETS
from market_forecast.persistence import RawArtifactStore, create_market_repository
from market_forecast.services.collection import MarketCollectionService
from market_forecast.sources import EntsoeSource, NbuExchangeRateSource, OperatorMarketSource


KYIV = ZoneInfo("Europe/Kyiv")
UKRAINE_ZONE = "10Y1001C--00003F"


@dataclass(frozen=True, slots=True)
class ContextDates:
    """Kyiv calendar dates used by one context refresh."""

    today: date
    tomorrow: date
    yesterday: date


@dataclass(frozen=True, slots=True)
class ContextRefreshResult:
    """Sanitized outcome for one independent context source."""

    source: str
    delivery_date: date
    status: str
    records: int = 0
    message: str | None = None


def context_dates(now: datetime | None = None) -> ContextDates:
    """Resolve today, tomorrow, and yesterday in the Kyiv calendar."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    today = current.astimezone(KYIV).date()
    return ContextDates(today, today + timedelta(days=1), today - timedelta(days=1))


def refresh_market_context(
    settings: Settings,
    now: datetime | None = None,
) -> list[ContextRefreshResult]:
    """Refresh FX, latest neighbor prices, yesterday flows, and recent volumes."""

    attempted_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    dates = context_dates(attempted_at)
    repository = create_market_repository(settings.database_path, settings.database_url)
    repository.initialize()
    service = MarketCollectionService(
        repository,
        RawArtifactStore(settings.raw_data_directory),
    )
    entsoe = EntsoeSource(
        settings.require_entsoe_token(),
        timeout_seconds=settings.request_timeout_seconds,
    )
    nbu = NbuExchangeRateSource(timeout_seconds=settings.request_timeout_seconds)
    results: list[ContextRefreshResult] = []

    def execute(source_name: str, delivery_date: date, operation) -> None:
        try:
            records = int(operation())
            result = ContextRefreshResult(
                source_name, delivery_date, "collected", records=records
            )
        except Exception as exc:
            result = ContextRefreshResult(
                source_name,
                delivery_date,
                "failed",
                message=type(exc).__name__,
            )
        repository.record_collection_attempt(
            result.source,
            result.delivery_date,
            attempted_at,
            result.status,
            result.records,
            result.message,
        )
        results.append(result)

    execute(
        "nbu_fx",
        dates.tomorrow,
        lambda: repository.store_exchange_rates(
            nbu.fetch_eur_rates(dates.today, dates.tomorrow), attempted_at
        ),
    )
    for market in NEIGHBOR_MARKETS:
        execute(
            f"entsoe_price_{market.code}",
            dates.today,
            lambda item=market: service.collect_entsoe(
                dates.today,
                entsoe,
                item.bidding_zone_eic,
            ).inserted_records,
        )
        for source_zone, target_zone, direction in (
            (market.bidding_zone_eic, UKRAINE_ZONE, "import"),
            (UKRAINE_ZONE, market.bidding_zone_eic, "export"),
        ):
            execute(
                f"entsoe_flow_{market.code}_{direction}",
                dates.yesterday,
                lambda source=source_zone, target=target_zone: service.collect_entsoe_flow(
                    dates.yesterday, entsoe, source, target
                ).inserted_records,
            )

    def refresh_operator_volumes() -> int:
        result = service.collect_operator_artifact(
            dates.today,
            OperatorMarketSource(timeout_seconds=settings.request_timeout_seconds),
        )
        if result is None:
            raise RuntimeError("Current Operator workbook is not published")
        return result.inserted_records

    execute("operator_volume", dates.today, refresh_operator_volumes)
    return results
