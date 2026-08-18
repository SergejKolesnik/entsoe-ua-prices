"""One-shot scheduled refresh with durable, user-visible outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from market_forecast.persistence import SQLiteMarketRepository
from market_forecast.services.collection import MarketCollectionService
from market_forecast.sources import OperatorMarketSource


KYIV = ZoneInfo("Europe/Kyiv")
OPERATOR_SOURCE = "operator_market"


@dataclass(frozen=True, slots=True)
class RefreshResult:
    """Outcome of one idempotent scheduled collection attempt."""

    delivery_date: date
    attempted_at_utc: datetime
    status: str
    inserted_records: int = 0
    message: str | None = None


def next_delivery_date(now: datetime | None = None) -> date:
    """Return tomorrow in Kyiv, independent of the host machine timezone."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(KYIV).date() + timedelta(days=1)


def refresh_operator_day(
    delivery_date: date,
    service: MarketCollectionService,
    source: OperatorMarketSource,
    repository: SQLiteMarketRepository,
    attempted_at_utc: datetime | None = None,
) -> RefreshResult:
    """Collect one operator day and always record a sanitized scheduler outcome."""

    attempted_at = attempted_at_utc or datetime.now(timezone.utc)
    if attempted_at.tzinfo is None:
        raise ValueError("attempted_at_utc must be timezone-aware")
    attempted_at = attempted_at.astimezone(timezone.utc)
    try:
        collected = service.collect_operator_artifact(delivery_date, source)
        if collected is None:
            result = RefreshResult(delivery_date, attempted_at, "unpublished")
        else:
            result = RefreshResult(
                delivery_date,
                attempted_at,
                "collected",
                inserted_records=collected.inserted_records,
            )
    except Exception as exc:  # scheduler must retain the failure for the dashboard
        result = RefreshResult(
            delivery_date,
            attempted_at,
            "failed",
            message=type(exc).__name__,
        )
    repository.record_collection_attempt(
        OPERATOR_SOURCE,
        result.delivery_date,
        result.attempted_at_utc,
        result.status,
        result.inserted_records,
        result.message,
    )
    return result
