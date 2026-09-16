"""Descriptive weather context for a completed RDN delivery day."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from market_forecast.domain import WeatherForecastPoint


KYIV = ZoneInfo("Europe/Kyiv")
DAYLIGHT_HOURS = range(10, 17)


@dataclass(frozen=True, slots=True)
class WeatherDayContext:
    """Unweighted six-point weather summary, never a causal market conclusion."""

    forecast_vintage_utc: datetime
    temperature_min_c: float
    temperature_max_c: float
    daylight_cloud_cover_percent: float
    daylight_radiation_wm2: float
    locations: int


def build_weather_day_context(
    points: Iterable[WeatherForecastPoint],
    delivery_date: date,
    expected_locations: int,
) -> WeatherDayContext | None:
    """Summarize complete regional forecasts for one Kyiv calendar day.

    The source has no calibrated national demand or generation weights, so the
    result is intentionally an unweighted regional description.
    """

    rows = [
        point for point in points
        if point.valid_start_utc.astimezone(KYIV).date() == delivery_date
    ]
    if not rows or len({point.location_id for point in rows}) != expected_locations:
        return None
    expected_periods = _period_count(delivery_date)
    if any(sum(point.location_id == location for point in rows) != expected_periods
           for location in {point.location_id for point in rows}):
        return None
    daylight = [
        point for point in rows
        if point.valid_start_utc.astimezone(KYIV).hour in DAYLIGHT_HOURS
    ]
    if not daylight:
        return None
    vintages = {point.forecast_vintage_utc for point in rows}
    if len(vintages) != 1:
        return None
    return WeatherDayContext(
        forecast_vintage_utc=vintages.pop(),
        temperature_min_c=min(float(point.temperature_c) for point in rows),
        temperature_max_c=max(float(point.temperature_c) for point in rows),
        daylight_cloud_cover_percent=sum(float(point.cloud_cover_percent) for point in daylight) / len(daylight),
        daylight_radiation_wm2=sum(float(point.shortwave_radiation_wm2) for point in daylight) / len(daylight),
        locations=expected_locations,
    )
def _period_count(day: date) -> int:
    from datetime import time, timedelta, timezone

    start = datetime.combine(day, time.min, KYIV).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, KYIV).astimezone(timezone.utc)
    return int((end - start).total_seconds() // 3600)
