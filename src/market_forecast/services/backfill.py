"""Controlled sequential historical collection."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from market_forecast.services.collection import CollectionResult


@dataclass(frozen=True, slots=True)
class BackfillDayResult:
    """Outcome for one requested delivery day."""

    delivery_date: date
    status: str
    inserted_records: int = 0
    message: str | None = None


def run_backfill(
    date_from: date,
    date_to: date,
    collect_day: Callable[[date], CollectionResult | None],
    delay_seconds: float = 0.5,
    max_days: int = 366,
) -> list[BackfillDayResult]:
    """Collect an inclusive date range while retaining every daily outcome."""

    days = list(iter_dates(date_from, date_to, max_days=max_days))
    if delay_seconds < 0:
        raise ValueError("delay_seconds must not be negative")

    results: list[BackfillDayResult] = []
    for index, delivery_date in enumerate(days):
        try:
            collected = collect_day(delivery_date)
            if collected is None:
                results.append(BackfillDayResult(delivery_date, "unpublished"))
            else:
                results.append(
                    BackfillDayResult(
                        delivery_date,
                        "collected",
                        inserted_records=collected.inserted_records,
                    )
                )
        except Exception as exc:  # daily isolation is the backfill contract
            results.append(
                BackfillDayResult(
                    delivery_date,
                    "failed",
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
        if delay_seconds and index < len(days) - 1:
            time.sleep(delay_seconds)
    return results


def iter_dates(date_from: date, date_to: date, max_days: int = 366):
    """Yield an inclusive, bounded date range."""

    if date_to < date_from:
        raise ValueError("date_to must not be before date_from")
    day_count = (date_to - date_from).days + 1
    if max_days < 1 or day_count > max_days:
        raise ValueError(f"Backfill range exceeds the {max_days}-day safety limit")
    for offset in range(day_count):
        yield date_from + timedelta(days=offset)
