"""Verified monthly gas history without invented daily values or plans."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class GasHistoryMonth:
    """Native VAT-inclusive annual-sheet values; volumes are normalized to m3."""

    reporting_month: date
    commodity_price: Decimal
    transportation_price: Decimal
    distribution_price: Decimal
    total_price: Decimal
    plant_volume_m3: Decimal
    sanatorium_volume_m3: Decimal
    total_volume_m3: Decimal
    amount_uah: Decimal

    def __post_init__(self) -> None:
        if type(self.reporting_month) is not date or self.reporting_month.day != 1:
            raise ValueError("History month must be the first day of a month")
        for value in (self.commodity_price, self.transportation_price, self.distribution_price,
                      self.total_price, self.plant_volume_m3, self.sanatorium_volume_m3,
                      self.total_volume_m3, self.amount_uah):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError("History values must be finite nonnegative Decimals")
        if abs(self.total_price - self.commodity_price - self.transportation_price
               - self.distribution_price) > Decimal("0.01"):
            raise ValueError("Gas history price components do not match")
        if self.total_volume_m3 != self.plant_volume_m3 + self.sanatorium_volume_m3:
            raise ValueError("Gas history volume components do not match")
        if abs(self.amount_uah - self.total_price * self.total_volume_m3 / 1000) > Decimal("0.01"):
            raise ValueError("Gas history amount does not match price times volume")
