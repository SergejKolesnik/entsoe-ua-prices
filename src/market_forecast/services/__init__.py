"""Application services coordinating sources, validation, and persistence."""

from .backfill import BackfillDayResult, run_backfill
from .collection import CollectionResult, MarketCollectionService
from .data_quality import DailyQuality, build_quality_report
from .scheduled_refresh import RefreshResult, next_delivery_date, refresh_operator_day
from .forecast_snapshots import SnapshotGenerationResult, generate_baseline_snapshot
from .neighbor_prices import aggregate_price_rows_hourly
from .report_export import build_daily_report, latest_operator_delivery_date, write_daily_report
from .context_refresh import (
    ContextDates,
    ContextRefreshResult,
    context_dates,
    refresh_market_context,
)

__all__ = [
    "BackfillDayResult",
    "CollectionResult",
    "DailyQuality",
    "MarketCollectionService",
    "build_quality_report",
    "run_backfill",
    "RefreshResult",
    "next_delivery_date",
    "refresh_operator_day",
    "SnapshotGenerationResult",
    "generate_baseline_snapshot",
    "aggregate_price_rows_hourly",
    "build_daily_report",
    "latest_operator_delivery_date",
    "write_daily_report",
    "ContextDates",
    "ContextRefreshResult",
    "context_dates",
    "refresh_market_context",
]
