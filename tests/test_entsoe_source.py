import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from market_forecast.sources.entsoe import API_URL, EntsoeSource


class FakeResponse:
    status_code = 200
    content = b"<Publication_MarketDocument />"
    headers = {"Content-Type": "application/xml"}
    url = API_URL + "?redacted=true"

    def raise_for_status(self) -> None:
        return None


class EntsoeSourceTests(unittest.TestCase):
    def test_builds_explicit_a44_request(self):
        session = Mock()
        session.get.return_value = FakeResponse()
        source = EntsoeSource("secret-token", session=session, timeout_seconds=9)
        start = datetime(2026, 8, 18, tzinfo=timezone.utc)

        result = source.fetch_day_ahead_prices(
            start,
            start + timedelta(days=1),
            "10Y1001C--00003F",
        )

        self.assertEqual(result.content_type, "application/xml")
        self.assertEqual(result.source_url, API_URL)
        self.assertNotIn("secret-token", result.source_url)
        _, kwargs = session.get.call_args
        self.assertEqual(session.get.call_args.args[0], API_URL)
        self.assertEqual(kwargs["params"]["documentType"], "A44")
        self.assertEqual(kwargs["params"]["processType"], "A01")
        self.assertEqual(kwargs["params"]["periodStart"], "202608180000")
        self.assertEqual(kwargs["params"]["periodEnd"], "202608190000")
        self.assertEqual(kwargs["timeout"], 9)

    def test_rejects_naive_timestamps(self):
        source = EntsoeSource("secret-token", session=Mock())
        start = datetime(2026, 8, 18)

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            source.fetch_day_ahead_prices(start, start + timedelta(days=1), "zone")

    def test_rejects_non_utc_timestamps(self):
        source = EntsoeSource("secret-token", session=Mock())
        offset = timezone(timedelta(hours=3))
        start = datetime(2026, 8, 18, tzinfo=offset)

        with self.assertRaisesRegex(ValueError, "must use UTC"):
            source.fetch_day_ahead_prices(start, start + timedelta(days=1), "zone")


if __name__ == "__main__":
    unittest.main()
