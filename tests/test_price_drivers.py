import unittest
from datetime import date

import pandas as pd

from market_forecast.analysis import build_price_driver_comparison, neighbor_daily_change


class PriceDriverComparisonTests(unittest.TestCase):
    def test_compares_latest_earlier_day_and_segments(self):
        prices = pd.DataFrame(
            [
                {"delivery_date": date(2026, 8, 19), "hour": hour, "price": 8_000}
                for hour in range(24)
            ]
            + [
                {
                    "delivery_date": date(2026, 8, 21),
                    "hour": hour,
                    "price": 1_000 if 10 <= hour <= 16 else 6_000,
                }
                for hour in range(24)
            ]
        )
        volumes = pd.DataFrame(
            [
                {"delivery_date": date(2026, 8, 19), "volume_mwh": 100},
                {"delivery_date": date(2026, 8, 21), "volume_mwh": 90},
            ]
        )

        result = build_price_driver_comparison(prices, volumes, date(2026, 8, 21))

        self.assertIsNotNone(result)
        self.assertEqual(result["previous_date"], date(2026, 8, 19))
        self.assertAlmostEqual(result["volume_change_percent"], -10)
        solar = result["segments"].set_index("Період").loc["Сонячні години"]
        self.assertEqual(solar["Поточна ціна"], 1_000)
        self.assertEqual(solar["Зміна, %"], -87.5)

    def test_returns_none_without_previous_day(self):
        prices = pd.DataFrame(
            [{"delivery_date": date(2026, 8, 21), "hour": 0, "price": 1_000}]
        )

        self.assertIsNone(
            build_price_driver_comparison(prices, pd.DataFrame(), date(2026, 8, 21))
        )

    def test_neighbor_change_uses_median_and_excludes_ukraine(self):
        rows = []
        for code, before, after in (
            ("UA", 100, 1_000),
            ("PL", 100, 110),
            ("SK", 200, 180),
        ):
            rows.extend(
                [
                    {"delivery_date": date(2026, 8, 20), "market_code": code, "price_eur": before},
                    {"delivery_date": date(2026, 8, 21), "market_code": code, "price_eur": after},
                ]
            )

        change = neighbor_daily_change(
            pd.DataFrame(rows), date(2026, 8, 21), date(2026, 8, 20)
        )

        self.assertAlmostEqual(change, 0.0)


if __name__ == "__main__":
    unittest.main()
