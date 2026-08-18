"""Normalized electricity price observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class HourlyMarketPrice:
    """One immutable price observation for a delivery interval."""

    delivery_start_utc: datetime
    delivery_end_utc: datetime
    price: Decimal
    currency: str
    bidding_zone: str
    market: str
    source: str
    settlement_period: int
    volume_mwh: Decimal | None = None
    source_revision: str | None = None

    def __post_init__(self) -> None:
        if self.delivery_start_utc.tzinfo is None or self.delivery_end_utc.tzinfo is None:
            raise ValueError("Delivery timestamps must be timezone-aware")
        if self.delivery_start_utc.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("delivery_start_utc must use UTC")
        if self.delivery_end_utc.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("delivery_end_utc must use UTC")
        if self.delivery_end_utc <= self.delivery_start_utc:
            raise ValueError("Delivery end must be after delivery start")
        if self.settlement_period < 1:
            raise ValueError("Settlement period must be positive")
        if not self.currency or not self.bidding_zone or not self.source:
            raise ValueError("Currency, bidding zone, and source are required")
