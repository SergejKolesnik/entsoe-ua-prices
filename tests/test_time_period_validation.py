import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_forecast.domain import HourlyMarketPrice
from market_forecast.validation import validate_delivery_periods


def make_records(count: int) -> list[HourlyMarketPrice]:
    start = datetime(2026, 3, 29, tzinfo=timezone.utc)
    return [
        HourlyMarketPrice(
            delivery_start_utc=start + timedelta(hours=index),
            delivery_end_utc=start + timedelta(hours=index + 1),
            price=Decimal("5000"),
            currency="UAH",
            bidding_zone="UA-IPS",
            market="day_ahead",
            source="operator_market",
            settlement_period=index + 1,
        )
        for index in range(count)
    ]


class TimePeriodValidationTests(unittest.TestCase):
    def test_accepts_23_24_and_25_period_days_when_explicit(self):
        for period_count in (23, 24, 25):
            with self.subTest(period_count=period_count):
                validate_delivery_periods(make_records(period_count), expected_periods=period_count)

    def test_rejects_missing_period(self):
        records = make_records(24)
        del records[11]

        with self.assertRaisesRegex(ValueError, "received 23"):
            validate_delivery_periods(records, expected_periods=24)

    def test_rejects_gap_even_without_expected_count(self):
        records = make_records(24)
        for index in range(12, len(records)):
            item = records[index]
            records[index] = HourlyMarketPrice(
                delivery_start_utc=item.delivery_start_utc + timedelta(hours=1),
                delivery_end_utc=item.delivery_end_utc + timedelta(hours=1),
                price=item.price,
                currency=item.currency,
                bidding_zone=item.bidding_zone,
                market=item.market,
                source=item.source,
                settlement_period=item.settlement_period,
            )

        with self.assertRaisesRegex(ValueError, "gap or overlap"):
            validate_delivery_periods(records)

    def test_rejects_duplicate_settlement_period(self):
        records = make_records(2)
        records[1] = HourlyMarketPrice(
            delivery_start_utc=records[1].delivery_start_utc,
            delivery_end_utc=records[1].delivery_end_utc,
            price=records[1].price,
            currency=records[1].currency,
            bidding_zone=records[1].bidding_zone,
            market=records[1].market,
            source=records[1].source,
            settlement_period=1,
        )

        with self.assertRaisesRegex(ValueError, "Duplicate settlement"):
            validate_delivery_periods(records)


if __name__ == "__main__":
    unittest.main()
