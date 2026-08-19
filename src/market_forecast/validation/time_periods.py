"""Settlement-period continuity checks."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from market_forecast.domain import HourlyMarketPrice


def validate_delivery_periods(
    records: Sequence[HourlyMarketPrice],
    expected_periods: int | None = None,
) -> None:
    """Validate one continuous uniform market series without repairing it."""

    if not records:
        raise ValueError("No delivery periods to validate")
    ordered = sorted(records, key=lambda item: item.delivery_start_utc)
    identity = {(item.source, item.market, item.bidding_zone, item.currency) for item in ordered}
    if len(identity) != 1:
        raise ValueError("Delivery periods mix different market series")
    if expected_periods is not None and len(ordered) != expected_periods:
        raise ValueError(f"Expected {expected_periods} periods, received {len(ordered)}")
    if len({item.settlement_period for item in ordered}) != len(ordered):
        raise ValueError("Duplicate settlement periods")
    if len({item.delivery_start_utc for item in ordered}) != len(ordered):
        raise ValueError("Duplicate delivery timestamps")

    durations = {
        item.delivery_end_utc - item.delivery_start_utc for item in ordered
    }
    if len(durations) != 1:
        raise ValueError("Delivery periods use mixed interval durations")
    duration = next(iter(durations))
    if duration not in {
        timedelta(minutes=15),
        timedelta(minutes=30),
        timedelta(hours=1),
    }:
        raise ValueError("Unsupported delivery interval duration")
    for previous, current in zip(ordered, ordered[1:]):
        if previous.delivery_end_utc != current.delivery_start_utc:
            raise ValueError("Delivery periods contain a gap or overlap")
