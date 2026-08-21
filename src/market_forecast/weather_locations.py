"""Small explicit regional weather grid for Ukrainian market diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class WeatherLocation:
    """A stable regional point; weights will be calibrated only with evidence."""

    code: str
    name_uk: str
    latitude: Decimal
    longitude: Decimal


WEATHER_LOCATIONS = (
    WeatherLocation("KYIV", "Київ", Decimal("50.4501"), Decimal("30.5234")),
    WeatherLocation("LVIV", "Львів", Decimal("49.8397"), Decimal("24.0297")),
    WeatherLocation("VIN", "Вінниця", Decimal("49.2331"), Decimal("28.4682")),
    WeatherLocation("ODESA", "Одеса", Decimal("46.4825"), Decimal("30.7233")),
    WeatherLocation("DNIPRO", "Дніпро", Decimal("48.4647"), Decimal("35.0462")),
    WeatherLocation("KHARKIV", "Харків", Decimal("49.9935"), Decimal("36.2304")),
)
