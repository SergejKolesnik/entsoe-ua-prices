"""Normalized hourly observations published for the Ukrainian intraday market."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class IntradayMarketResult:
    """One immutable official VDR result for a Kyiv delivery interval."""

    delivery_start_utc: datetime
    delivery_end_utc: datetime
    settlement_period: int
    weighted_price_uah_per_mwh: Decimal
    minimum_price_uah_per_mwh: Decimal
    maximum_price_uah_per_mwh: Decimal
    last_price_uah_per_mwh: Decimal
    sale_volume_mwh: Decimal
    purchase_volume_mwh: Decimal
    declared_sale_volume_mwh: Decimal
    declared_purchase_volume_mwh: Decimal
    source: str = "operator_intraday"

    def __post_init__(self) -> None:
        if self.delivery_start_utc.tzinfo is None or self.delivery_end_utc.tzinfo is None:
            raise ValueError("Delivery timestamps must be timezone-aware")
        if self.delivery_start_utc.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("delivery_start_utc must use UTC")
        if self.delivery_end_utc.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("delivery_end_utc must use UTC")
        if self.delivery_end_utc - self.delivery_start_utc != timedelta(hours=1):
            raise ValueError("An intraday result must cover exactly one hour")
        if self.settlement_period < 1:
            raise ValueError("Settlement period must be positive")
        if not self.source:
            raise ValueError("Source is required")
        values = (
            self.weighted_price_uah_per_mwh,
            self.minimum_price_uah_per_mwh,
            self.maximum_price_uah_per_mwh,
            self.last_price_uah_per_mwh,
            self.sale_volume_mwh,
            self.purchase_volume_mwh,
            self.declared_sale_volume_mwh,
            self.declared_purchase_volume_mwh,
        )
        if any(value < 0 for value in values):
            raise ValueError("Intraday prices and volumes must be non-negative")
        if self.minimum_price_uah_per_mwh > self.maximum_price_uah_per_mwh:
            raise ValueError("Minimum intraday price exceeds maximum price")
        if not self.minimum_price_uah_per_mwh <= self.weighted_price_uah_per_mwh <= self.maximum_price_uah_per_mwh:
            raise ValueError("Weighted intraday price lies outside its range")
        if not self.minimum_price_uah_per_mwh <= self.last_price_uah_per_mwh <= self.maximum_price_uah_per_mwh:
            raise ValueError("Last intraday price lies outside its range")
        if self.sale_volume_mwh != self.purchase_volume_mwh:
            raise ValueError("Official intraday sale and purchase volumes must match")
