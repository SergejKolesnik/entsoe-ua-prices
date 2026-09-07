"""Normalized internal natural-gas procurement observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class GasProcurementMonth:
    """One monthly price composition imported from the internal source sheet."""

    reporting_month: date
    commodity_price_uah_per_1000m3: Decimal
    distribution_price_uah_per_1000m3: Decimal
    capacity_price_uah_per_1000m3: Decimal
    total_price_uah_per_1000m3: Decimal
    planned_volume_m3: Decimal
    vat_included: bool
    source_sheet: str


@dataclass(frozen=True, slots=True)
class GasConsumptionDay:
    """One daily planned-versus-actual gas-consumption observation."""

    delivery_date: date
    planned_volume_m3: Decimal
    actual_volume_m3: Decimal | None
    source_sheet: str
