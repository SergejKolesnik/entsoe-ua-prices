"""Period selection and matrices for comparable weekly DAM heatmaps."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd


@dataclass(frozen=True)
class ComparisonPeriods:
    """Two explicit inclusive periods used by a heatmap comparison."""

    current_start: date
    current_end: date
    comparison_start: date
    comparison_end: date


@dataclass(frozen=True)
class WeeklyHeatmapComparison:
    """Aligned means, observation counts, and current-minus-comparison change."""

    current: pd.DataFrame
    comparison: pd.DataFrame
    current_counts: pd.DataFrame
    comparison_counts: pd.DataFrame
    difference: pd.DataFrame


def rolling_periods(selected_date: date, days: int = 30) -> ComparisonPeriods:
    """Compare the inclusive trailing window with the immediately prior window."""

    if days <= 0:
        raise ValueError("days must be positive")
    current_start = selected_date - timedelta(days=days - 1)
    comparison_end = current_start - timedelta(days=1)
    return ComparisonPeriods(
        current_start=current_start,
        current_end=selected_date,
        comparison_start=comparison_end - timedelta(days=days - 1),
        comparison_end=comparison_end,
    )


def year_over_year_month_periods(selected_date: date) -> ComparisonPeriods:
    """Compare month-to-date with the same calendar span one year earlier."""

    prior_year = selected_date.year - 1
    prior_day = min(
        selected_date.day,
        calendar.monthrange(prior_year, selected_date.month)[1],
    )
    return ComparisonPeriods(
        current_start=selected_date.replace(day=1),
        current_end=selected_date,
        comparison_start=date(prior_year, selected_date.month, 1),
        comparison_end=date(prior_year, selected_date.month, prior_day),
    )


def build_weekly_heatmap_comparison(
    frame: pd.DataFrame, periods: ComparisonPeriods
) -> WeeklyHeatmapComparison:
    """Build aligned 7x24 mean and count matrices for two periods."""

    required = {"delivery_date", "delivery_start", "hour", "price"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing heatmap columns: {', '.join(sorted(missing))}")
    current_rows = _select(frame, periods.current_start, periods.current_end)
    comparison_rows = _select(
        frame, periods.comparison_start, periods.comparison_end
    )
    current, current_counts = _matrix(current_rows)
    comparison, comparison_counts = _matrix(comparison_rows)
    return WeeklyHeatmapComparison(
        current=current,
        comparison=comparison,
        current_counts=current_counts,
        comparison_counts=comparison_counts,
        difference=current - comparison,
    )


def _select(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return frame[
        (frame["delivery_date"] >= start) & (frame["delivery_date"] <= end)
    ].copy()


def _matrix(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    index = range(7)
    columns = range(24)
    if rows.empty:
        empty = pd.DataFrame(index=index, columns=columns, dtype=float)
        return empty, empty.fillna(0).astype(int)
    rows["weekday"] = rows["delivery_start"].dt.weekday
    means = rows.pivot_table(
        index="weekday", columns="hour", values="price", aggfunc="mean"
    ).reindex(index=index, columns=columns)
    counts = rows.pivot_table(
        index="weekday", columns="hour", values="price", aggfunc="count"
    ).reindex(index=index, columns=columns, fill_value=0)
    return means, counts.astype(int)
