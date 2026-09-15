"""Daily refresh of supporting market context with isolated outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo

from market_forecast.config import Settings
from market_forecast.neighbor_markets import NEIGHBOR_MARKETS
from market_forecast.parsers import parse_operator_market_workbook
from market_forecast.persistence import RawArtifactStore, create_market_repository
from market_forecast.services.collection import MarketCollectionService
from market_forecast.sources import (
    EntsoeSource,
    NbuExchangeRateSource,
    OpenMeteoSource,
    OperatorMarketSource,
    parse_open_meteo_forecast,
)
from market_forecast.weather_locations import WEATHER_LOCATIONS


KYIV = ZoneInfo("Europe/Kyiv")
UKRAINE_ZONE = "10Y1001C--00003F"
ENTSOE_HTTP_ERROR = re.compile(
    r"^ENTSO-E request failed with HTTP status (?P<status>[1-5][0-9]{2})$"
)
ENTSOE_VALUE_ERROR_CODES = (
    ("ENTSO-E XML document is empty", "entsoe_empty_document"),
    ("ENTSO-E response is not valid XML", "entsoe_invalid_xml"),
    (
        "ENTSO-E response is not a price publication document",
        "entsoe_invalid_publication",
    ),
    ("ENTSO-E TimeSeries has no currency", "entsoe_missing_currency"),
    ("ENTSO-E TimeSeries has no bidding zone", "entsoe_missing_bidding_zone"),
    ("Unsupported ENTSO-E price resolution", "entsoe_unsupported_resolution"),
    ("ENTSO-E period end must be after start", "entsoe_invalid_period"),
    (
        "ENTSO-E point contains invalid position or price",
        "entsoe_invalid_point",
    ),
    ("ENTSO-E position must be positive", "entsoe_invalid_position"),
    ("ENTSO-E period contains duplicate positions", "entsoe_duplicate_positions"),
    ("ENTSO-E period is not aligned to its resolution", "entsoe_misaligned_period"),
    ("ENTSO-E point falls outside declared period", "entsoe_point_outside_period"),
    ("ENTSO-E document contains no price points", "entsoe_no_price_points"),
    (
        "ENTSO-E document contains conflicting duplicate prices",
        "entsoe_conflicting_duplicate_prices",
    ),
    (
        "ENTSO-E prices do not overlap the requested delivery day",
        "entsoe_no_overlap",
    ),
    (
        "ENTSO-E prices do not cover the requested delivery day",
        "entsoe_incomplete_day",
    ),
    ("No delivery periods to validate", "delivery_periods_empty"),
    ("Delivery periods mix different market series", "delivery_periods_mixed_series"),
    ("Expected ", "delivery_period_count_mismatch"),
    ("Duplicate settlement periods", "delivery_period_duplicate_settlements"),
    ("Duplicate delivery timestamps", "delivery_period_duplicate_timestamps"),
    ("Delivery periods use mixed interval durations", "delivery_period_mixed_durations"),
    ("Unsupported delivery interval duration", "delivery_period_unsupported_duration"),
    ("Delivery periods contain a gap or overlap", "delivery_period_gap_or_overlap"),
)


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


def _sanitized_failure_message(exc: Exception) -> str:
    """Return an allowlisted diagnostic without source URLs or response bodies."""

    match = ENTSOE_HTTP_ERROR.fullmatch(str(exc))
    if isinstance(exc, RuntimeError) and match:
        return f"RuntimeError:http_{match.group('status')}"
    if isinstance(exc, ValueError):
        message = str(exc)
        for fragment, code in ENTSOE_VALUE_ERROR_CODES:
            if fragment in message:
                return f"ValueError:{code}"
        return "ValueError:validation_error"
    return type(exc).__name__


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
    weather = OpenMeteoSource(timeout_seconds=settings.request_timeout_seconds)
    results: list[ContextRefreshResult] = []

    def day_bounds(delivery_date: date) -> tuple[datetime, datetime]:
        start = datetime.combine(delivery_date, time.min, KYIV).astimezone(timezone.utc)
        end = datetime.combine(
            delivery_date + timedelta(days=1), time.min, KYIV
        ).astimezone(timezone.utc)
        return start, end

    def refresh_neighbor_price(market) -> int:
        start, end = day_bounds(dates.today)
        if repository.list_prices("entsoe", start, end, market.bidding_zone_eic):
            return 0
        return service.collect_entsoe(
            dates.today,
            entsoe,
            market.bidding_zone_eic,
        ).inserted_records

    def refresh_border_flow(source_zone: str, target_zone: str) -> int:
        start, end = day_bounds(dates.yesterday)
        existing = repository.list_flows(start, end)
        if any(row[2] == source_zone and row[3] == target_zone for row in existing):
            return 0
        return service.collect_entsoe_flow(
            dates.yesterday, entsoe, source_zone, target_zone
        ).inserted_records

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
                message=_sanitized_failure_message(exc),
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

    def refresh_weather_forecast() -> int:
        raw = weather.fetch(WEATHER_LOCATIONS, forecast_days=3)
        vintage = attempted_at.replace(minute=0, second=0, microsecond=0)
        points = parse_open_meteo_forecast(raw.content, WEATHER_LOCATIONS, vintage)
        artifact = service.artifact_store.save(
            raw.content, "open_meteo", dates.tomorrow, "json"
        )
        return repository.store_weather_forecast(
            artifact, raw.source_url, attempted_at, points
        )

    execute("open_meteo", dates.tomorrow, refresh_weather_forecast)
    for market in NEIGHBOR_MARKETS:
        execute(
            f"entsoe_price_{market.code}",
            dates.today,
            lambda item=market: refresh_neighbor_price(item),
        )
        for source_zone, target_zone, direction in (
            (market.bidding_zone_eic, UKRAINE_ZONE, "import"),
            (UKRAINE_ZONE, market.bidding_zone_eic, "export"),
        ):
            execute(
                f"entsoe_flow_{market.code}_{direction}",
                dates.yesterday,
                lambda source=source_zone, target=target_zone: refresh_border_flow(
                    source, target
                ),
            )

    def refresh_operator_volumes() -> int:
        source = OperatorMarketSource(timeout_seconds=settings.request_timeout_seconds)
        observation = source.discover(dates.today)
        if observation is None:
            raise RuntimeError("Current Operator workbook is not published")
        raw = source.download(observation)
        records = parse_operator_market_workbook(raw.content, dates.today)
        return repository.enrich_price_volumes(records)

    execute("operator_volume", dates.today, refresh_operator_volumes)
    return results
