"""Normalized cross-border physical electricity flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CrossBorderFlow:
    """Average physical power sent from one bidding zone to another."""

    delivery_start_utc: datetime
    delivery_end_utc: datetime
    source_zone: str
    target_zone: str
    power_mw: Decimal
    source_revision: str | None = None

    def __post_init__(self) -> None:
        if self.delivery_start_utc.tzinfo is None or self.delivery_end_utc.tzinfo is None:
            raise ValueError("Flow timestamps must be timezone-aware")
        if self.delivery_start_utc.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("delivery_start_utc must use UTC")
        if self.delivery_end_utc.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("delivery_end_utc must use UTC")
        if self.delivery_end_utc <= self.delivery_start_utc:
            raise ValueError("Flow delivery end must be after start")
        if not self.source_zone or not self.target_zone:
            raise ValueError("Flow source and target zones are required")
        if self.source_zone == self.target_zone:
            raise ValueError("Flow source and target zones must differ")

