import unittest
from datetime import date

import pandas as pd

from market_forecast.analysis.seasonality import (
    build_monthly_seasonality_profile,
    build_year_over_year_month,
)


class SeasonalityTests(unittest.TestCase):
    def test_year_over_year_uses_only_matching_calendar_days(self):
        daily = pd.DataFrame(
            {
                "delivery_date": [
                    date(2025, 8, 1),
                    date(2025, 8, 2),
                    date(2025, 8, 3),
                    date(2026, 8, 1),
                    date(2026, 8, 3),
                    date(2026, 8, 4),
                ],
                "average": [100, 200, 300, 200, 600, 900],
            }
        )

        result = build_year_over_year_month(
            daily, date(2026, 8, 4), minimum_matched_days=2
        )

        self.assertEqual(result.matched_days, 2)
        self.assertEqual(result.status, "partial_overlap")
        self.assertEqual(result.points["day"].tolist(), [1, 3])
        self.assertEqual(result.current_average, 400.0)
        self.assertEqual(result.prior_average, 200.0)
        self.assertEqual(result.change_percent, 100.0)

    def test_year_over_year_reports_missing_prior_period(self):
        daily = pd.DataFrame(
            {"delivery_date": [date(2026, 9, 1)], "average": [5000]}
        )

        result = build_year_over_year_month(daily, date(2026, 9, 1))

        self.assertEqual(result.status, "no_prior_period")
        self.assertIsNone(result.change_percent)
        self.assertTrue(result.points.empty)

    def test_monthly_profile_counts_distinct_years(self):
        daily = pd.DataFrame(
            {
                "delivery_date": [
                    date(2024, 9, 1),
                    date(2025, 9, 1),
                    date(2025, 10, 1),
                ],
                "average": [100, 300, 500],
            }
        )

        profile = build_monthly_seasonality_profile(daily).set_index("month")

        self.assertEqual(profile.loc[9, "years"], 2)
        self.assertEqual(profile.loc[9, "seasonal_average"], 200.0)
        self.assertEqual(profile.loc[10, "years"], 1)

    def test_missing_columns_fail_visibly(self):
        with self.assertRaisesRegex(ValueError, "average"):
            build_year_over_year_month(
                pd.DataFrame({"delivery_date": [date(2026, 1, 1)]}),
                date(2026, 1, 1),
            )


if __name__ == "__main__":
    unittest.main()
