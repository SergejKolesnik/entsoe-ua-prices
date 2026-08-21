"""Transparent day-over-day diagnostics for Ukrainian DAM prices."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


PRICE_SEGMENTS = (
    ("Ніч", 0, 5),
    ("Ранок", 6, 9),
    ("Сонячні години", 10, 16),
    ("Вечірній пік", 17, 22),
    ("Пізній вечір", 23, 23),
)


def build_price_driver_comparison(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    selected_date: date,
) -> dict[str, Any] | None:
    """Compare a delivery day with the latest earlier observed day.

    The result deliberately contains observations only. It does not assign causal
    weights to weather, generation, or market behaviour that are not in the input.
    """

    required_price_columns = {"delivery_date", "hour", "price"}
    if prices.empty or not required_price_columns.issubset(prices.columns):
        return None
    current = prices[prices["delivery_date"] == selected_date].copy()
    previous_dates = sorted(
        day for day in prices["delivery_date"].dropna().unique() if day < selected_date
    )
    if current.empty or not previous_dates:
        return None
    previous_date = previous_dates[-1]
    previous = prices[prices["delivery_date"] == previous_date].copy()

    current_average = float(current["price"].mean())
    previous_average = float(previous["price"].mean())
    absolute_change = current_average - previous_average
    percent_change = (
        absolute_change / previous_average * 100 if previous_average else None
    )

    segment_rows: list[dict[str, Any]] = []
    for label, start_hour, end_hour in PRICE_SEGMENTS:
        current_segment = current[current["hour"].between(start_hour, end_hour)]
        previous_segment = previous[previous["hour"].between(start_hour, end_hour)]
        if current_segment.empty or previous_segment.empty:
            continue
        current_value = float(current_segment["price"].mean())
        previous_value = float(previous_segment["price"].mean())
        segment_rows.append(
            {
                "Період": label,
                "Години": f"{start_hour:02d}:00–{end_hour:02d}:59",
                "Поточна ціна": current_value,
                "Попередня ціна": previous_value,
                "Зміна": current_value - previous_value,
                "Зміна, %": (
                    (current_value - previous_value) / previous_value * 100
                    if previous_value
                    else None
                ),
            }
        )

    current_volume = _daily_volume(volumes, selected_date)
    previous_volume = _daily_volume(volumes, previous_date)
    volume_change_percent = None
    if current_volume is not None and previous_volume:
        volume_change_percent = (current_volume - previous_volume) / previous_volume * 100

    return {
        "selected_date": selected_date,
        "previous_date": previous_date,
        "current_average": current_average,
        "previous_average": previous_average,
        "absolute_change": absolute_change,
        "percent_change": percent_change,
        "current_volume": current_volume,
        "previous_volume": previous_volume,
        "volume_change_percent": volume_change_percent,
        "low_price_hours": int((current["price"] <= 1_000).sum()),
        "segments": pd.DataFrame(segment_rows),
    }


def neighbor_daily_change(
    frame: pd.DataFrame, selected_date: date, previous_date: date
) -> float | None:
    """Return the median neighboring-market daily price change in percent."""

    required_columns = {"delivery_date", "market_code", "price_eur"}
    if frame.empty or not required_columns.issubset(frame.columns):
        return None
    neighbors = frame[frame["market_code"] != "UA"]
    daily = neighbors.groupby(["delivery_date", "market_code"])["price_eur"].mean()
    changes = []
    for code in neighbors["market_code"].unique():
        current_key = (selected_date, code)
        previous_key = (previous_date, code)
        if current_key not in daily.index or previous_key not in daily.index:
            continue
        previous_value = float(daily.loc[previous_key])
        if previous_value:
            changes.append(
                (float(daily.loc[current_key]) - previous_value) / previous_value * 100
            )
    return float(pd.Series(changes).median()) if changes else None


def _daily_volume(volumes: pd.DataFrame, delivery_date: date) -> float | None:
    if volumes.empty or not {"delivery_date", "volume_mwh"}.issubset(volumes.columns):
        return None
    rows = volumes[volumes["delivery_date"] == delivery_date]["volume_mwh"].dropna()
    return float(rows.sum()) if not rows.empty else None
