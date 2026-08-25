"""Official-style Ukrainian DAM price indices and regulatory cap diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pandas as pd


PEAK_HOURS = frozenset(range(8, 20))


@dataclass(frozen=True)
class DailyPriceIndices:
    """Arithmetic Base, Peak and Offpeak indices for one delivery day."""

    base: float
    peak: float
    offpeak: float
    period_count: int


@dataclass(frozen=True)
class PriceCapRegime:
    """One effective-dated DAM price-cap regime backed by a public decision."""

    effective_from: date
    effective_to: date | None
    minimum_uah_mwh: float
    maximum_uah_mwh: float
    resolution: str
    source_url: str

    def applies_on(self, delivery_date: date) -> bool:
        """Return whether the regime is effective for the delivery date."""

        return self.effective_from <= delivery_date and (
            self.effective_to is None or delivery_date <= self.effective_to
        )


# Only independently verified regimes belong here. Earlier dates deliberately return
# no cap instead of inheriting today's regulatory values backwards.
PRICE_CAP_REGIMES = (
    PriceCapRegime(
        effective_from=date(2026, 4, 30),
        effective_to=None,
        minimum_uah_mwh=10.0,
        maximum_uah_mwh=15_000.0,
        resolution="Постанова НКРЕКП від 23.04.2026 № 621",
        source_url="https://zakon.rada.gov.ua/go/v0621874-26",
    ),
)


def calculate_daily_price_indices(rows: pd.DataFrame) -> DailyPriceIndices | None:
    """Calculate Operator-style indices from local delivery hours.

    The Market Operator defines Peak as settlement periods 09:00–20:00 and
    Offpeak as 01:00–08:00 plus 21:00–24:00. In zero-based local clock hours,
    Peak is therefore 08:00–19:59. DST days may contain 23, 24 or 25 periods.
    """

    if rows.empty or not {"hour", "price"}.issubset(rows.columns):
        return None
    clean = rows[["hour", "price"]].copy()
    clean["price"] = pd.to_numeric(clean["price"], errors="coerce")
    clean["hour"] = pd.to_numeric(clean["hour"], errors="coerce")
    clean = clean.dropna()
    if clean.empty:
        return None
    peak = clean[clean["hour"].isin(PEAK_HOURS)]["price"]
    offpeak = clean[~clean["hour"].isin(PEAK_HOURS)]["price"]
    if peak.empty or offpeak.empty:
        return None
    return DailyPriceIndices(
        base=float(clean["price"].mean()),
        peak=float(peak.mean()),
        offpeak=float(offpeak.mean()),
        period_count=len(clean),
    )


def price_cap_for_date(
    delivery_date: date,
    regimes: Iterable[PriceCapRegime] = PRICE_CAP_REGIMES,
) -> PriceCapRegime | None:
    """Return the single verified regime for a date, or ``None`` when unknown."""

    matches = [regime for regime in regimes if regime.applies_on(delivery_date)]
    if len(matches) > 1:
        raise ValueError("Overlapping DAM price-cap regimes")
    return matches[0] if matches else None


def price_cap_diagnostics(
    rows: pd.DataFrame,
    regime: PriceCapRegime | None,
    proximity_ratio: float = 0.95,
) -> dict[str, float | int] | None:
    """Summarize observed proximity to a verified maximum DAM price cap."""

    if regime is None or rows.empty or "price" not in rows:
        return None
    prices = pd.to_numeric(rows["price"], errors="coerce").dropna()
    if prices.empty:
        return None
    maximum = regime.maximum_uah_mwh
    return {
        "maximum_cap": maximum,
        "maximum_price": float(prices.max()),
        "maximum_utilization_percent": float(prices.max() / maximum * 100),
        "near_cap_periods": int((prices >= maximum * proximity_ratio).sum()),
        "period_count": len(prices),
    }
