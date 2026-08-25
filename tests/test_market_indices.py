"""Tests for official-style daily indices and effective-dated price caps."""

import unittest
from datetime import date

import pandas as pd

from market_forecast.analysis import (
    PriceCapRegime,
    calculate_daily_price_indices,
    price_cap_diagnostics,
    price_cap_for_date,
)


class MarketIndexTests(unittest.TestCase):
    def test_calculates_base_peak_and_offpeak(self):
        frame = pd.DataFrame(
            {"hour": range(24), "price": [100.0] * 8 + [200.0] * 12 + [50.0] * 4}
        )

        result = calculate_daily_price_indices(frame)

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.base, 3400.0 / 24)
        self.assertAlmostEqual(result.peak, 200.0)
        self.assertAlmostEqual(result.offpeak, 50.0 * 4 / 12 + 100.0 * 8 / 12)
        self.assertEqual(result.period_count, 24)

    def test_keeps_valid_dst_period_count(self):
        frame = pd.DataFrame(
            {"hour": [0, 1, 3, *range(4, 24)], "price": [100.0] * 23}
        )

        result = calculate_daily_price_indices(frame)

        self.assertIsNotNone(result)
        self.assertEqual(result.period_count, 23)

    def test_returns_none_when_one_index_segment_is_missing(self):
        frame = pd.DataFrame({"hour": range(8), "price": [100.0] * 8})

        self.assertIsNone(calculate_daily_price_indices(frame))

    def test_selects_only_effective_verified_regime(self):
        self.assertIsNone(price_cap_for_date(date(2026, 4, 29)))
        regime = price_cap_for_date(date(2026, 4, 30))
        self.assertIsNotNone(regime)
        self.assertEqual(regime.maximum_uah_mwh, 15_000.0)

    def test_rejects_overlapping_regimes(self):
        regimes = [
            PriceCapRegime(date(2026, 1, 1), None, 10, 100, "a", "https://a"),
            PriceCapRegime(date(2026, 1, 2), None, 10, 200, "b", "https://b"),
        ]

        with self.assertRaisesRegex(ValueError, "Overlapping"):
            price_cap_for_date(date(2026, 1, 2), regimes)

    def test_cap_diagnostics_use_95_percent_threshold(self):
        regime = price_cap_for_date(date(2026, 8, 25))
        frame = pd.DataFrame({"price": [10_000, 14_250, 15_000]})

        result = price_cap_diagnostics(frame, regime)

        self.assertEqual(result["near_cap_periods"], 2)
        self.assertEqual(result["maximum_utilization_percent"], 100.0)


if __name__ == "__main__":
    unittest.main()
