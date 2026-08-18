import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

from market_forecast.services import build_quality_report


class DataQualityTests(unittest.TestCase):
    def test_reports_complete_and_missing_days(self):
        repository = Mock()
        start = datetime(2026, 7, 31, 21, tzinfo=timezone.utc)
        repository.list_prices.return_value = [
            (start + timedelta(hours=index), Decimal(index + 1)) for index in range(24)
        ]

        report = build_quality_report(
            repository,
            date(2026, 8, 1),
            date(2026, 8, 2),
            "operator_market",
        )

        self.assertEqual(report[0].status, "complete")
        self.assertEqual(report[0].actual_periods, 24)
        self.assertEqual(report[0].minimum_price, Decimal("1"))
        self.assertEqual(report[0].maximum_price, Decimal("24"))
        self.assertEqual(report[0].average_price, Decimal("12.5"))
        self.assertEqual(report[1].status, "missing")
        self.assertEqual(report[1].actual_periods, 0)

    def test_expects_23_periods_on_spring_dst_day(self):
        repository = Mock()
        start = datetime(2026, 3, 28, 22, tzinfo=timezone.utc)
        repository.list_prices.return_value = [
            (start + timedelta(hours=index), Decimal("100")) for index in range(23)
        ]

        report = build_quality_report(
            repository,
            date(2026, 3, 29),
            date(2026, 3, 29),
            "operator_market",
        )

        self.assertEqual(report[0].expected_periods, 23)
        self.assertEqual(report[0].status, "complete")

    def test_json_representation_uses_strings_for_decimals(self):
        repository = Mock()
        repository.list_prices.return_value = []
        item = build_quality_report(
            repository,
            date(2026, 8, 1),
            date(2026, 8, 1),
            "operator_market",
        )[0]

        self.assertEqual(item.to_dict()["delivery_date"], "2026-08-01")
        self.assertIsNone(item.to_dict()["average_price"])


if __name__ == "__main__":
    unittest.main()
