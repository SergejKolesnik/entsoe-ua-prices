"""Generate immutable operational forecast vintages from validated market history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_forecast.forecasting import build_day_forecast, walk_forward_backtest
from market_forecast.persistence import SQLiteMarketRepository


KYIV = ZoneInfo("Europe/Kyiv")
SOURCE = "operator_market"
MODEL_VERSION = "baseline-v1"


@dataclass(frozen=True, slots=True)
class SnapshotGenerationResult:
    """Summary of an immutable operational forecast snapshot."""

    forecast_run_id: int
    target_delivery_date: date
    model_name: str
    model_version: str
    points: int
    created: bool


def generate_baseline_snapshot(
    repository: SQLiteMarketRepository,
    issued_at_utc: datetime | None = None,
) -> SnapshotGenerationResult:
    """Backtest candidates, select the lower-MAE baseline, and freeze its next forecast."""

    issued_at = issued_at_utc or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise ValueError("issued_at_utc must be timezone-aware")
    issued_at = issued_at.astimezone(timezone.utc)
    available = repository.available_period(SOURCE)
    if available is None:
        raise ValueError("No validated Operator Market history is available")
    earliest, latest_timestamp = available
    rows = repository.list_prices(SOURCE, earliest, latest_timestamp + timedelta(hours=1))
    comparison = walk_forward_backtest(rows)
    champion = comparison.champion_method
    metrics = (
        comparison.comparable_day
        if champion == "comparable_day"
        else comparison.previous_day
    )
    training_cutoff = latest_timestamp.astimezone(KYIV).date()
    target_date = training_cutoff + timedelta(days=1)
    forecast = build_day_forecast(rows, target_date, champion)
    if not forecast:
        raise ValueError("Baseline could not produce a forecast snapshot")
    interval = metrics.absolute_error_p80
    points = [
        (
            item.delivery_start_utc,
            item.predicted_price,
            max(Decimal(0), item.predicted_price - interval),
            item.predicted_price + interval,
            item.method,
            item.sample_count,
        )
        for item in forecast
    ]
    run_id, created = repository.store_forecast_snapshot(
        target_delivery_date=target_date,
        issued_at_utc=issued_at,
        training_cutoff_date=training_cutoff,
        model_name=champion,
        model_version=MODEL_VERSION,
        backtest_days=metrics.evaluated_days,
        backtest_observations=metrics.observations,
        mae=metrics.mae,
        rmse=metrics.rmse,
        absolute_error_p80=metrics.absolute_error_p80,
        points=points,
    )
    return SnapshotGenerationResult(
        run_id,
        target_date,
        champion,
        MODEL_VERSION,
        len(points),
        created,
    )
