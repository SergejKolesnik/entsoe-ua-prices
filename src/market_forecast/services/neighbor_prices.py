"""Resolution-safe transformations for comparing neighboring DAM prices."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal


def aggregate_price_rows_hourly(
    rows: list[tuple[datetime, Decimal]],
) -> list[tuple[datetime, Decimal]]:
    """Average complete 15/30/60-minute price groups into aligned UTC hours."""

    grouped: dict[datetime, list[Decimal]] = defaultdict(list)
    for timestamp, price in rows:
        if timestamp.tzinfo is None:
            raise ValueError("Price timestamps must be timezone-aware")
        utc = timestamp.astimezone(timezone.utc)
        hour = utc.replace(minute=0, second=0, microsecond=0)
        grouped[hour].append(price)
    result: list[tuple[datetime, Decimal]] = []
    for hour, prices in sorted(grouped.items()):
        if len(prices) not in {1, 2, 4}:
            raise ValueError(f"Incomplete or mixed market intervals for {hour.isoformat()}")
        result.append((hour, sum(prices, Decimal(0)) / len(prices)))
    return result
