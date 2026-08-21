"""Open-Meteo raw forecast client and strict hourly parser."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

import requests

from market_forecast.domain import WeatherForecastPoint
from market_forecast.sources.base import RawResponse
from market_forecast.weather_locations import WeatherLocation


API_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = (
    "temperature_2m",
    "cloud_cover",
    "shortwave_radiation",
    "wind_speed_100m",
)


class OpenMeteoSource:
    """Fetch a multi-location forecast without persistence or aggregation."""

    def __init__(self, session: requests.Session | None = None, timeout_seconds: float = 30.0):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def fetch(self, locations: Iterable[WeatherLocation], forecast_days: int = 3) -> RawResponse:
        """Return one raw response for an explicit regional point set."""

        points = tuple(locations)
        if not points:
            raise ValueError("At least one weather location is required")
        if not 1 <= forecast_days <= 7:
            raise ValueError("forecast_days must be between 1 and 7")
        response = self.session.get(
            API_URL,
            params={
                "latitude": ",".join(str(point.latitude) for point in points),
                "longitude": ",".join(str(point.longitude) for point in points),
                "hourly": ",".join(HOURLY_VARIABLES),
                "timezone": "UTC",
                "forecast_days": forecast_days,
                "wind_speed_unit": "kmh",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        raw = RawResponse(
            content=response.content,
            content_type=response.headers.get("Content-Type", ""),
            status_code=response.status_code,
            source_url=API_URL,
        )
        raw.require_content()
        return raw


def parse_open_meteo_forecast(
    content: bytes,
    locations: Iterable[WeatherLocation],
    forecast_vintage_utc: datetime,
) -> list[WeatherForecastPoint]:
    """Parse a multi-location JSON response with exact ordering validation."""

    if forecast_vintage_utc.tzinfo is None or forecast_vintage_utc.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("forecast_vintage_utc must use UTC")
    points = tuple(locations)
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Open-Meteo returned invalid JSON") from exc
    responses = payload if isinstance(payload, list) else [payload]
    if len(responses) != len(points):
        raise ValueError("Open-Meteo location count does not match the request")

    records: list[WeatherForecastPoint] = []
    for location, response in zip(points, responses):
        try:
            latitude = Decimal(str(response["latitude"]))
            longitude = Decimal(str(response["longitude"]))
            hourly = response["hourly"]
            timestamps = hourly["time"]
            series = [hourly[name] for name in HOURLY_VARIABLES]
        except (KeyError, TypeError, InvalidOperation) as exc:
            raise ValueError("Open-Meteo response is missing required fields") from exc
        if abs(latitude - location.latitude) > Decimal("0.2") or abs(longitude - location.longitude) > Decimal("0.2"):
            raise ValueError("Open-Meteo response location does not match the request")
        if not timestamps or any(len(values) != len(timestamps) for values in series):
            raise ValueError("Open-Meteo hourly series are incomplete")
        for index, raw_time in enumerate(timestamps):
            try:
                valid_start = datetime.fromisoformat(raw_time).replace(tzinfo=timezone.utc)
                values = [Decimal(str(items[index])) for items in series]
            except (TypeError, ValueError, InvalidOperation) as exc:
                raise ValueError("Open-Meteo contains an invalid hourly value") from exc
            records.append(
                WeatherForecastPoint(
                    location_id=location.code,
                    latitude=latitude,
                    longitude=longitude,
                    forecast_vintage_utc=forecast_vintage_utc,
                    valid_start_utc=valid_start,
                    temperature_c=values[0],
                    cloud_cover_percent=values[1],
                    shortwave_radiation_wm2=values[2],
                    wind_speed_100m_kmh=values[3],
                )
            )
    return records
