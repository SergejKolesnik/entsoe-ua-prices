"""Tests for explicit comparable weekly heatmap periods."""

import unittest
from datetime import date

import pandas as pd

from market_forecast.analysis import (
    build_weekly_heatmap_comparison,
    rolling_periods,
    year_over_year_month_periods,
)


class HeatmapComparisonTests(unittest.TestCase):
    def test_rolling_periods_are_adjacent_and_equal(self):
        periods = rolling_periods(date(2026, 8, 25), 30)

        self.assertEqual(periods.current_start, date(2026, 7, 27))
        self.assertEqual(periods.current_end, date(2026, 8, 25))
        self.assertEqual(periods.comparison_start, date(2026, 6, 27))
        self.assertEqual(periods.comparison_end, date(2026, 7, 26))

    def test_year_over_year_uses_same_month_to_date(self):
        periods = year_over_year_month_periods(date(2026, 8, 25))

        self.assertEqual(periods.current_start, date(2026, 8, 1))
        self.assertEqual(periods.current_end, date(2026, 8, 25))
        self.assertEqual(periods.comparison_start, date(2025, 8, 1))
        self.assertEqual(periods.comparison_end, date(2025, 8, 25))

    def test_matrices_align_means_counts_and_difference(self):
        timestamps = pd.to_datetime(
            ["2026-08-03T08:00:00+03:00", "2026-08-10T08:00:00+03:00"]
        )
        frame = pd.DataFrame(
            {
                "delivery_date": [date(2026, 8, 3), date(2026, 8, 10)],
                "delivery_start": timestamps,
                "hour": [8, 8],
                "price": [100.0, 140.0],
            }
        )
        periods = rolling_periods(date(2026, 8, 10), 7)

        result = build_weekly_heatmap_comparison(frame, periods)

        self.assertEqual(result.current.loc[0, 8], 140.0)
        self.assertEqual(result.comparison.loc[0, 8], 100.0)
        self.assertEqual(result.current_counts.loc[0, 8], 1)
        self.assertEqual(result.difference.loc[0, 8], 40.0)

    def test_missing_comparison_stays_missing_not_zero(self):
        timestamp = pd.to_datetime(["2026-08-10T08:00:00+03:00"])
        frame = pd.DataFrame(
            {
                "delivery_date": [date(2026, 8, 10)],
                "delivery_start": timestamp,
                "hour": [8],
                "price": [140.0],
            }
        )

        result = build_weekly_heatmap_comparison(
            frame, rolling_periods(date(2026, 8, 10), 7)
        )

        self.assertTrue(pd.isna(result.comparison.loc[0, 8]))
        self.assertTrue(pd.isna(result.difference.loc[0, 8]))
        self.assertEqual(result.comparison_counts.loc[0, 8], 0)


if __name__ == "__main__":
    unittest.main()
