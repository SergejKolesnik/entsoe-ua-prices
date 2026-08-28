import unittest
from datetime import date, datetime, timezone

import streamlit_app


class FakeRepository:
    def __init__(self, periods):
        self.periods = periods

    def available_period(self, source, bidding_zone=None):
        return self.periods.get((source, bidding_zone))


class SidebarContextTests(unittest.TestCase):
    def test_expected_delivery_periods_follow_kyiv_dst(self):
        self.assertEqual(streamlit_app._expected_delivery_periods(date(2026, 3, 29)), 23)
        self.assertEqual(streamlit_app._expected_delivery_periods(date(2026, 8, 29)), 24)
        self.assertEqual(streamlit_app._expected_delivery_periods(date(2026, 10, 25)), 25)

    def test_neighbor_freshness_uses_latest_common_date(self):
        periods = {}
        for index, market in enumerate(streamlit_app.NEIGHBOR_MARKETS):
            latest = datetime(2026, 8, 28 - index, 21, tzinfo=timezone.utc)
            periods[("entsoe", market.bidding_zone_eic)] = (
                datetime(2025, 8, 1, tzinfo=timezone.utc),
                latest,
            )

        common = streamlit_app._latest_common_neighbor_date(FakeRepository(periods))

        self.assertEqual(common, date(2026, 8, 26))

    def test_neighbor_freshness_is_unavailable_when_one_market_is_missing(self):
        repository = FakeRepository({})

        self.assertIsNone(streamlit_app._latest_common_neighbor_date(repository))


if __name__ == "__main__":
    unittest.main()
