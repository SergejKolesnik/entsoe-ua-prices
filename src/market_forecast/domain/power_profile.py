"""Validated hourly internal electricity-consumption observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PowerProfileObservation:
    """One one-hour source observation from the internal profile workbook."""

    delivery_date: date
    hour: int
    planned_purchase_mwh: Decimal | None
    purchased_mwh: Decimal | None
    gpu_mwh: Decimal | None
    ses_mwh: Decimal | None
    grid_export_mwh: Decimal | None
    technology_consumption_mwh: Decimal | None
    power_consumption_mwh: Decimal | None
    imbalance_mwh: Decimal | None
    source_sheet: str

    def __post_init__(self) -> None:
        if not 0 <= self.hour < 24:
            raise ValueError("hour must be between 0 and 23")
        values = (
            self.planned_purchase_mwh, self.purchased_mwh, self.gpu_mwh,
            self.ses_mwh, self.grid_export_mwh, self.technology_consumption_mwh,
            self.power_consumption_mwh, self.imbalance_mwh,
        )
        if all(value is None for value in values):
            raise ValueError("power profile row has no numeric observations")
        if not self.source_sheet.strip():
            raise ValueError("source_sheet must not be empty")
