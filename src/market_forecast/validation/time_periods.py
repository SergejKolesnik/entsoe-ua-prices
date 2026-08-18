"""Settlement-period continuity checks."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from market_forecast.domain import HourlyMarketPrice


def validate_delivery_periods(
    records: Sequence[HourlyMarketPrice],
    expected_periods: int | None = None,
) -> None:
    """Validate a single continuous hourly market series without repairing it."""

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

    for item in ordered:
        if item.delivery_end_utc - item.delivery_start_utc != timedelta(hours=1):
            raise ValueError("Expected hourly delivery intervals")
    for previous, current in zip(ordered, ordered[1:]):
        if previous.delivery_end_utc != current.delivery_start_utc:
            raise ValueError("Delivery periods contain a gap or overlap")
