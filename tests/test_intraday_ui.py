"""Selection rules for the VDR hourly comparison."""

from datetime import date
import unittest

import streamlit_app as app


class IntradayUiTests(unittest.TestCase):
    def test_completed_day_quick_choices_are_bounded_by_available_dates(self) -> None:
        available = [date(2026, 9, 13), date(2026, 9, 14), date(2026, 9, 15)]
        self.assertEqual(available[-1], date(2026, 9, 15))
        self.assertIn(date(2026, 9, 14), available)

    def test_uses_requested_date_when_available(self) -> None:
        self.assertEqual(
            app._nearest_intraday_date([date(2026, 9, 13), date(2026, 9, 14)], date(2026, 9, 14)),
            date(2026, 9, 14),
        )

    def test_uses_nearest_available_date_and_prefers_earlier_on_a_tie(self) -> None:
        self.assertEqual(
            app._nearest_intraday_date([date(2026, 9, 13), date(2026, 9, 15)], date(2026, 9, 14)),
            date(2026, 9, 13),
        )

    def test_rejects_empty_coverage(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one"):
            app._nearest_intraday_date([], date(2026, 9, 14))
