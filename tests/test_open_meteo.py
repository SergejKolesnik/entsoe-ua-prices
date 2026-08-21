import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository
from market_forecast.sources import OpenMeteoSource, parse_open_meteo_forecast
from market_forecast.weather_locations import WEATHER_LOCATIONS


class _Response:
    status_code = 200
    headers = {"Content-Type": "application/json"}
    url = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, response):
        self.response = response
        self.params = None

    def get(self, _url, *, params, timeout):
        self.params = params
        self.timeout = timeout
        return self.response


def _payload(locations, hours=2):
    timestamps = [f"2026-08-22T{hour:02d}:00" for hour in range(hours)]
    return [
        {
            "latitude": float(location.latitude),
            "longitude": float(location.longitude),
            "hourly": {
                "time": timestamps,
                "temperature_2m": [20 + index] * hours,
                "cloud_cover": [10 + index] * hours,
                "shortwave_radiation": [0, 100][:hours],
                "wind_speed_100m": [12 + index] * hours,
            },
        }
        for index, location in enumerate(locations)
    ]


class OpenMeteoTests(unittest.TestCase):
    def test_client_requests_utc_hourly_regional_forecast(self):
        locations = WEATHER_LOCATIONS[:2]
        content = json.dumps(_payload(locations)).encode()
        session = _Session(_Response(content))

        raw = OpenMeteoSource(session=session).fetch(locations, forecast_days=3)

        self.assertEqual(raw.content, content)
        self.assertEqual(session.params["timezone"], "UTC")
        self.assertEqual(session.params["forecast_days"], 3)
        self.assertIn("shortwave_radiation", session.params["hourly"])

    def test_parser_and_repository_keep_immutable_vintage(self):
        locations = WEATHER_LOCATIONS[:2]
        content = json.dumps(_payload(locations)).encode()
        vintage = datetime(2026, 8, 21, 14, tzinfo=timezone.utc)
        records = parse_open_meteo_forecast(content, locations, vintage)
        self.assertEqual(len(records), 4)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            repository.initialize()
            artifact = RawArtifactStore(root / "raw").save(
                content, "open_meteo", records[0].valid_start_utc.date(), "json"
            )
            inserted = repository.store_weather_forecast(
                artifact,
                "https://api.open-meteo.com/v1/forecast",
                vintage + timedelta(minutes=20),
                records,
            )
            repeated = repository.store_weather_forecast(
                artifact,
                "https://api.open-meteo.com/v1/forecast",
                vintage + timedelta(minutes=25),
                records,
            )
            loaded = repository.list_weather_forecasts(
                records[0].valid_start_utc,
                records[-1].valid_start_utc + timedelta(hours=1),
                vintage,
            )

        self.assertEqual(inserted, 4)
        self.assertEqual(repeated, 0)
        self.assertEqual(loaded, records)

    def test_parser_rejects_incomplete_series(self):
        locations = WEATHER_LOCATIONS[:1]
        payload = _payload(locations)
        payload[0]["hourly"]["cloud_cover"] = []

        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_open_meteo_forecast(
                json.dumps(payload).encode(),
                locations,
                datetime(2026, 8, 21, 14, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
