"""Calendar-aligned, descriptive seasonality analysis for validated daily prices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class YearOverYearMonth:
    """Matched month-to-date observations for an anchor year and its predecessor."""

    anchor: date
    current_year: int
    prior_year: int
    matched_days: int
    expected_days: int
    current_average: float | None
    prior_average: float | None
    change_percent: float | None
    status: str
    points: pd.DataFrame


def build_year_over_year_month(
    daily: pd.DataFrame,
    anchor: date,
    *,
    minimum_matched_days: int = 7,
) -> YearOverYearMonth:
    """Compare identical calendar days in ``anchor`` month with the prior year.

    Only day numbers present in both years are compared. This prevents a partial
    month from being compared with a full month and keeps missing days visible.
    """

    required = {"delivery_date", "average"}
    missing = required.difference(daily.columns)
    if missing:
        raise ValueError(f"Missing daily columns: {', '.join(sorted(missing))}")
    if minimum_matched_days < 1:
        raise ValueError("minimum_matched_days must be positive")

    prepared = daily.loc[:, ["delivery_date", "average"]].copy()
    prepared["delivery_date"] = pd.to_datetime(prepared["delivery_date"], errors="coerce")
    prepared["average"] = pd.to_numeric(prepared["average"], errors="coerce")
    prepared = prepared.dropna(subset=["delivery_date", "average"])
    prepared["year"] = prepared["delivery_date"].dt.year
    prepared["month"] = prepared["delivery_date"].dt.month
    prepared["day"] = prepared["delivery_date"].dt.day

    current_year = anchor.year
    prior_year = current_year - 1
    cutoff_day = anchor.day
    current = prepared[
        (prepared["year"] == current_year)
        & (prepared["month"] == anchor.month)
        & (prepared["day"] <= cutoff_day)
    ].set_index("day")["average"]
    prior = prepared[
        (prepared["year"] == prior_year)
        & (prepared["month"] == anchor.month)
        & (prepared["day"] <= cutoff_day)
    ].set_index("day")["average"]

    matched = sorted(set(current.index).intersection(prior.index))
    points = pd.DataFrame(
        {
            "day": matched,
            "current": [float(current.loc[item]) for item in matched],
            "prior": [float(prior.loc[item]) for item in matched],
        }
    )
    matched_days = len(points)
    current_average = float(points["current"].mean()) if matched_days else None
    prior_average = float(points["prior"].mean()) if matched_days else None
    change_percent = None
    if prior_average not in (None, 0.0) and current_average is not None:
        change_percent = (current_average / prior_average - 1.0) * 100.0

    if matched_days == 0:
        status = "no_prior_period"
    elif matched_days < minimum_matched_days:
        status = "limited_overlap"
    elif matched_days < cutoff_day:
        status = "partial_overlap"
    else:
        status = "comparable"

    return YearOverYearMonth(
        anchor=anchor,
        current_year=current_year,
        prior_year=prior_year,
        matched_days=matched_days,
        expected_days=cutoff_day,
        current_average=current_average,
        prior_average=prior_average,
        change_percent=change_percent,
        status=status,
        points=points,
    )


def build_monthly_seasonality_profile(daily: pd.DataFrame) -> pd.DataFrame:
    """Return monthly averages with an explicit count of represented years."""

    required = {"delivery_date", "average"}
    missing = required.difference(daily.columns)
    if missing:
        raise ValueError(f"Missing daily columns: {', '.join(sorted(missing))}")

    prepared = daily.loc[:, ["delivery_date", "average"]].copy()
    prepared["delivery_date"] = pd.to_datetime(prepared["delivery_date"], errors="coerce")
    prepared["average"] = pd.to_numeric(prepared["average"], errors="coerce")
    prepared = prepared.dropna(subset=["delivery_date", "average"])
    prepared["year"] = prepared["delivery_date"].dt.year
    prepared["month"] = prepared["delivery_date"].dt.month

    by_year = (
        prepared.groupby(["year", "month"], as_index=False)
        .agg(average=("average", "mean"), observed_days=("delivery_date", "nunique"))
    )
    if by_year.empty:
        return pd.DataFrame(
            columns=["month", "seasonal_average", "minimum", "maximum", "years", "observed_months"]
        )
    return (
        by_year.groupby("month", as_index=False)
        .agg(
            seasonal_average=("average", "mean"),
            minimum=("average", "min"),
            maximum=("average", "max"),
            years=("year", "nunique"),
            observed_months=("year", "size"),
        )
        .sort_values("month")
    )
