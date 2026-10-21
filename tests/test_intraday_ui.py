"""Selection rules for the VDR hourly comparison."""

from datetime import date
import unittest

import pandas as pd

import streamlit_app as app


class IntradayUiTests(unittest.TestCase):
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

    def test_power_profile_ignores_rows_for_unfilled_future_day(self) -> None:
        rows = []
        for delivery_date in (date(2026, 10, 19), date(2026, 10, 20)):
            for hour in range(24):
                complete = delivery_date == date(2026, 10, 19)
                rows.append({
                    "delivery_date": delivery_date,
                    "hour": hour,
                    "purchased_mwh": 10 if complete else None,
                    "power_consumption_mwh": 8 if complete else None,
                    "grid_export_mwh": 1 if complete else None,
                })

        dates = app._complete_power_profile_dates(pd.DataFrame(rows), date(2026, 10, 20))

        self.assertEqual(dates, [date(2026, 10, 19)])
