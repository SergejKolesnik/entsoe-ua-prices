"""Tests for the independent daily market-context refresh."""

import unittest
from datetime import date, datetime, timezone

from market_forecast.cli import build_parser
from market_forecast.services import context_dates
from market_forecast.services.context_refresh import _sanitized_failure_message


class ContextRefreshTests(unittest.TestCase):
    """Verify Kyiv calendar boundaries and CLI registration."""

    def test_allows_only_entsoe_http_status_in_failure_message(self):
        self.assertEqual(
            _sanitized_failure_message(
                RuntimeError("ENTSO-E request failed with HTTP status 401")
            ),
            "RuntimeError:http_401",
        )

    def test_unknown_failure_detail_remains_hidden(self):
        message = _sanitized_failure_message(
            RuntimeError("secret token in https://example.test/private")
        )

        self.assertEqual(message, "RuntimeError")
        self.assertNotIn("secret", message)

    def test_context_dates_use_kyiv_calendar(self):
        instant = datetime(2026, 8, 19, 21, 30, tzinfo=timezone.utc)

        result = context_dates(instant)

        self.assertEqual(result.today, date(2026, 8, 20))
        self.assertEqual(result.tomorrow, date(2026, 8, 21))
        self.assertEqual(result.yesterday, date(2026, 8, 19))

    def test_context_dates_reject_naive_datetime(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            context_dates(datetime(2026, 8, 20, 12, 0))

    def test_refresh_context_command_is_registered(self):
        args = build_parser().parse_args(["refresh-context"])

        self.assertEqual(args.command, "refresh-context")


if __name__ == "__main__":
    unittest.main()
