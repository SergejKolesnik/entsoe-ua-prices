"""Weather forecast observations available before electricity delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class WeatherForecastPoint:
    """One hourly regional weather forecast from one collection vintage."""

    location_id: str
    latitude: Decimal
    longitude: Decimal
    forecast_vintage_utc: datetime
    valid_start_utc: datetime
    temperature_c: Decimal
    cloud_cover_percent: Decimal
    shortwave_radiation_wm2: Decimal
    wind_speed_100m_kmh: Decimal
    source: str = "open_meteo"
    model: str = "best_match"

    def __post_init__(self) -> None:
        for name, value in (
            ("forecast_vintage_utc", self.forecast_vintage_utc),
            ("valid_start_utc", self.valid_start_utc),
        ):
            if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(None):
                raise ValueError(f"{name} must use UTC")
        if not self.location_id or not self.source or not self.model:
            raise ValueError("Weather identity fields are required")
        if not Decimal("0") <= self.cloud_cover_percent <= Decimal("100"):
            raise ValueError("Cloud cover must be between 0 and 100 percent")
        if self.shortwave_radiation_wm2 < 0 or self.wind_speed_100m_kmh < 0:
            raise ValueError("Radiation and wind speed must not be negative")
