import unittest
from datetime import date

from market_forecast.services import CollectionResult, run_backfill
from market_forecast.services.backfill import iter_dates


class BackfillTests(unittest.TestCase):
    def test_retains_collected_unpublished_and_failed_days(self):
        def collect(day: date):
            if day == date(2026, 8, 1):
                return CollectionResult("operator_market", day, "a" * 64, 24, 24)
            if day == date(2026, 8, 2):
                return None
            raise ValueError("broken workbook")

        results = run_backfill(
            date(2026, 8, 1),
            date(2026, 8, 3),
            collect,
            delay_seconds=0,
        )

        self.assertEqual([item.status for item in results], ["collected", "unpublished", "failed"])
        self.assertEqual(results[0].inserted_records, 24)
        self.assertIn("broken workbook", results[2].message)

    def test_rejects_reversed_range(self):
        with self.assertRaisesRegex(ValueError, "before"):
            list(iter_dates(date(2026, 8, 2), date(2026, 8, 1)))

    def test_enforces_explicit_safety_limit(self):
        with self.assertRaisesRegex(ValueError, "2-day safety limit"):
            list(iter_dates(date(2026, 8, 1), date(2026, 8, 3), max_days=2))


if __name__ == "__main__":
    unittest.main()
