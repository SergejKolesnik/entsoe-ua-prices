from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import TestCase

from market_forecast.neighbor_markets import MARKET_BY_CODE, MARKET_BY_EIC, NEIGHBOR_MARKETS
from market_forecast.services import aggregate_price_rows_hourly


class NeighborPriceTests(TestCase):
    def test_registry_has_unique_verified_market_identities(self):
        self.assertEqual(set(MARKET_BY_CODE), {"PL", "SK", "HU", "RO"})
        self.assertEqual(len(MARKET_BY_EIC), len(NEIGHBOR_MARKETS))

    def test_aggregates_four_quarter_hours_to_one_utc_hour(self):
        start = datetime(2026, 8, 20, 10, tzinfo=timezone.utc)
        rows = [
            (start + timedelta(minutes=15 * index), Decimal(value))
            for index, value in enumerate(("50", "60", "70", "80"))
        ]

        hourly = aggregate_price_rows_hourly(rows)

        self.assertEqual(hourly, [(start, Decimal("65"))])

    def test_rejects_incomplete_quarter_hour_group(self):
        start = datetime(2026, 8, 20, 10, tzinfo=timezone.utc)
        rows = [
            (start + timedelta(minutes=15 * index), Decimal("50"))
            for index in range(3)
        ]

        with self.assertRaisesRegex(ValueError, "Incomplete or mixed"):
            aggregate_price_rows_hourly(rows)
