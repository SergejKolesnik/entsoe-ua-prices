"""Transparent hourly baselines that use only data available before each cutoff."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from statistics import median
from zoneinfo import ZoneInfo


KYIV = ZoneInfo("Europe/Kyiv")
PriceRow = tuple[datetime, Decimal]


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """One auditable hourly forecast value."""

    delivery_start_utc: datetime
    predicted_price: Decimal
    method: str
    sample_count: int


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    """Out-of-sample error metrics for one baseline."""

    method: str
    evaluated_days: int
    observations: int
    mae: Decimal
    rmse: Decimal
    mape_percent: Decimal | None
    absolute_error_p80: Decimal


@dataclass(frozen=True, slots=True)
class BacktestComparison:
    """Comparable-day and previous-day results evaluated on identical cutoffs."""

    comparable_day: BacktestMetrics
    previous_day: BacktestMetrics

    @property
    def champion_method(self) -> str:
        """Choose the lower-MAE baseline without privileging the newer method."""

        if self.comparable_day.mae < self.previous_day.mae:
            return "comparable_day"
        return "previous_day"


def build_day_forecast(
    rows: list[PriceRow],
    target_date: date,
    method: str = "comparable_day",
    lookback_weeks: int = 4,
    minimum_weekday_samples: int = 2,
) -> list[ForecastPoint]:
    """Forecast a Kyiv delivery day using observations strictly before it."""

    if method not in {"comparable_day", "previous_day"}:
        raise ValueError("Unsupported baseline method")
    if lookback_weeks <= 0 or minimum_weekday_samples <= 0:
        raise ValueError("Lookback and sample thresholds must be positive")
    history = _history_index(rows, before=target_date)
    target_start = datetime.combine(target_date, time.min, KYIV).astimezone(timezone.utc)
    target_end = datetime.combine(target_date + timedelta(days=1), time.min, KYIV).astimezone(
        timezone.utc
    )
    result: list[ForecastPoint] = []
    delivery_start = target_start
    while delivery_start < target_end:
        local = delivery_start.astimezone(KYIV)
        key = (local.hour, local.fold)
        previous = _lookup_hour(history, target_date - timedelta(days=1), *key)
        samples: list[Decimal] = []
        if method == "comparable_day":
            for weeks_ago in range(1, lookback_weeks + 1):
                value = _lookup_hour(
                    history, target_date - timedelta(days=7 * weeks_ago), *key
                )
                if value is not None:
                    samples.append(value)
        if method == "previous_day" or len(samples) < minimum_weekday_samples:
            if previous is None:
                previous = _latest_prior_hour(history, target_date, *key)
            if previous is None:
                delivery_start += timedelta(hours=1)
                continue
            prediction = previous
            point_method = (
                "previous_day"
                if history.get((target_date - timedelta(days=1), *key)) is not None
                else "recent_hour"
            )
            sample_count = 1
        else:
            prediction = Decimal(str(median(samples)))
            point_method = "comparable_day"
            sample_count = len(samples)
        result.append(ForecastPoint(delivery_start, prediction, point_method, sample_count))
        delivery_start += timedelta(hours=1)
    return result


def walk_forward_backtest(
    rows: list[PriceRow],
    minimum_training_days: int = 14,
) -> BacktestComparison:
    """Evaluate both baselines chronologically on the same complete delivery days."""

    if minimum_training_days < 7:
        raise ValueError("minimum_training_days must be at least 7")
    actual = {timestamp: price for timestamp, price in rows}
    dates = sorted({timestamp.astimezone(KYIV).date() for timestamp, _ in rows})
    comparable_errors: list[tuple[Decimal, Decimal]] = []
    previous_errors: list[tuple[Decimal, Decimal]] = []
    evaluated_days = 0
    for index, target_date in enumerate(dates):
        if index < minimum_training_days:
            continue
        comparable = build_day_forecast(rows, target_date, "comparable_day")
        previous = build_day_forecast(rows, target_date, "previous_day")
        comparable_by_time = {item.delivery_start_utc: item for item in comparable}
        previous_by_time = {item.delivery_start_utc: item for item in previous}
        target_actual = {
            timestamp: price
            for timestamp, price in actual.items()
            if timestamp.astimezone(KYIV).date() == target_date
        }
        if not target_actual or set(target_actual) != set(comparable_by_time) or set(
            target_actual
        ) != set(previous_by_time):
            continue
        evaluated_days += 1
        for timestamp, value in target_actual.items():
            comparable_errors.append((value, comparable_by_time[timestamp].predicted_price))
            previous_errors.append((value, previous_by_time[timestamp].predicted_price))
    if not comparable_errors:
        raise ValueError("Not enough complete history for walk-forward evaluation")
    return BacktestComparison(
        _metrics("comparable_day", evaluated_days, comparable_errors),
        _metrics("previous_day", evaluated_days, previous_errors),
    )


def _history_index(rows: list[PriceRow], before: date) -> dict[tuple[date, int, int], Decimal]:
    result: dict[tuple[date, int, int], Decimal] = {}
    for timestamp, price in rows:
        if timestamp.tzinfo is None:
            raise ValueError("Price timestamps must be timezone-aware")
        normalized = timestamp.astimezone(timezone.utc)
        local = normalized.astimezone(KYIV)
        if local.date() < before:
            result[(local.date(), local.hour, local.fold)] = price
    return result


def _lookup_hour(
    history: dict[tuple[date, int, int], Decimal],
    delivery_date: date,
    hour: int,
    fold: int,
) -> Decimal | None:
    """Use the normal occurrence as proxy for a rare repeated DST hour."""

    value = history.get((delivery_date, hour, fold))
    if value is None and fold == 1:
        return history.get((delivery_date, hour, 0))
    return value


def _latest_prior_hour(
    history: dict[tuple[date, int, int], Decimal],
    target_date: date,
    hour: int,
    fold: int,
) -> Decimal | None:
    """Find the most recent available matching hour for DST or source gaps."""

    matching = [
        (delivery_date, value)
        for (delivery_date, stored_hour, stored_fold), value in history.items()
        if delivery_date < target_date
        and stored_hour == hour
        and (stored_fold == fold or fold == 1 and stored_fold == 0)
    ]
    return max(matching, default=(None, None), key=lambda item: item[0])[1]


def _metrics(
    method: str,
    evaluated_days: int,
    observations: list[tuple[Decimal, Decimal]],
) -> BacktestMetrics:
    errors = [abs(actual - predicted) for actual, predicted in observations]
    mae = sum(errors, Decimal(0)) / len(errors)
    mse = sum((actual - predicted) ** 2 for actual, predicted in observations) / len(errors)
    nonzero = [(actual, predicted) for actual, predicted in observations if actual != 0]
    mape = None
    if nonzero:
        mape = (
            sum(abs(actual - predicted) / abs(actual) for actual, predicted in nonzero)
            / len(nonzero)
            * 100
        )
    ordered = sorted(errors)
    p80_index = max(0, math.ceil(len(ordered) * 0.8) - 1)
    return BacktestMetrics(
        method,
        evaluated_days,
        len(observations),
        mae,
        Decimal(str(math.sqrt(float(mse)))),
        mape,
        ordered[p80_index],
    )
